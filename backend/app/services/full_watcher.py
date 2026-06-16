"""Modo FULL: varre sub-pastas (uma por TipoEnvio) na ordem definida pelo painel,
processa em lotes com intervalo entre eles, e revisita a cada N horas durante o dia.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, date, timedelta
from pathlib import Path

from sqlalchemy.orm import Session

from ..config import settings
from ..database import SessionLocal
from .. import models
from . import (
    envio_service,
    notificacoes_service,
    pdf_service,
    cliente_crypto,
    soc_service,
    file_provenance,
)


log = logging.getLogger("full_watcher")


class FullWatcher:
    def __init__(self) -> None:
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_daily_scan_date: date | None = None
        self._last_full_run: datetime | None = None

    def start(self) -> None:
        if not settings.full_enabled:
            log.info("Modo FULL desativado (.env FULL_ENABLED=false)")
            return
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="full-watcher")
        self._thread.start()
        log.info(
            "Modo FULL iniciado - pasta=%s",
            settings.data_path(settings.full_watch_folder),
        )

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    # -------------- loop --------------
    def _run(self) -> None:
        pasta = settings.data_path(settings.full_watch_folder)
        pasta.mkdir(parents=True, exist_ok=True)
        while not self._stop.is_set():
            db: Session = SessionLocal()
            try:
                rc = db.get(models.RuntimeConfig, 1)
                scan_active = rc.full_scan_active if rc else True
                modo_ativo = rc.full_modo_ativo if rc else True
                interval = rc.full_scan_interval_seconds if rc else settings.full_scan_interval_seconds
                exec_time = rc.full_scan_exec_time if rc else "08:00"
                rescan_horas = rc.full_rescan_horas if rc else 1
            finally:
                db.close()

            interval = max(10, min(3600, int(interval)))

            if scan_active and modo_ativo:
                try:
                    if soc_service.is_soc_locked(db):
                        log.warning("FULL ignorado: modo SOC ativo")
                    elif self._deve_executar_agora(exec_time, rescan_horas):
                        self._scan_completo(pasta)
                except Exception as e:
                    log.exception("Erro no watcher FULL: %s", e)
            else:
                log.debug("FULL pausado (interruptor desligado)")

            self._stop.wait(interval)

    def _deve_executar_agora(self, exec_time: str | None, rescan_horas: int) -> bool:
        """Executa no horário programado e re-executa a cada N horas no mesmo dia."""
        agora = datetime.now()
        hoje = agora.date()

        # Sem horário definido: scan a cada interval
        if not exec_time or len(exec_time) != 5 or exec_time[2] != ":":
            return True
        try:
            hora = int(exec_time[0:2])
            minuto = int(exec_time[3:5])
        except Exception:
            return True

        momento_programado = agora.replace(hour=hora, minute=minuto, second=0, microsecond=0)
        if agora < momento_programado:
            return False

        # Primeira execucao do dia
        if self._last_daily_scan_date != hoje:
            self._last_daily_scan_date = hoje
            self._last_full_run = agora
            return True

        # Re-scan a cada rescan_horas (0 = só uma vez por dia)
        if rescan_horas <= 0:
            return False
        if self._last_full_run is None:
            self._last_full_run = agora
            return True
        if agora - self._last_full_run >= timedelta(hours=rescan_horas):
            self._last_full_run = agora
            return True
        return False

    def _scan_completo(self, pasta_raiz: Path) -> None:
        """Processa cada TipoEnvio na ordem do painel.

        Para cada tipo: pega PDFs em <raiz>/<codigo>/, processa em lotes
        de full_lote_size com intervalo de full_intervalo_lote_min minutos.
        Quando todos os tipos forem percorridos, ainda processa PDFs soltos
        na raiz (sem tipo).
        """
        db: Session = SessionLocal()
        try:
            rc = db.get(models.RuntimeConfig, 1)
            lote = rc.full_lote_size if rc else settings.full_lote_size
            intervalo_min = rc.full_intervalo_lote_min if rc else settings.full_intervalo_lote_min
            tipos = (
                db.query(models.TipoEnvio)
                .filter(models.TipoEnvio.ativo == True, models.TipoEnvio.na_fila_full == True)  # noqa: E712
                .order_by(models.TipoEnvio.ordem.asc(), models.TipoEnvio.id.asc())
                .all()
            )
        finally:
            db.close()

        lote = max(1, min(200, int(lote)))
        intervalo_seg = max(0, int(intervalo_min)) * 60

        for tipo in tipos:
            sub = pasta_raiz / tipo.codigo
            if not sub.is_dir():
                sub.mkdir(parents=True, exist_ok=True)
                continue
            self._scan_pasta(sub, tipo_codigo=tipo.codigo, lote=lote, intervalo_seg=intervalo_seg)

        # PDFs na raiz (compatibilidade com fluxo antigo)
        self._scan_pasta(pasta_raiz, tipo_codigo=None, lote=lote, intervalo_seg=intervalo_seg)

    def _scan_pasta(
        self, pasta: Path, *, tipo_codigo: str | None, lote: int, intervalo_seg: int
    ) -> None:
        pdfs = sorted(p for p in pasta.glob("*.pdf") if p.is_file())
        if not pdfs:
            return

        log.info(
            "FULL: %d PDF(s) em %s (tipo=%s, lote=%d, intervalo=%ds)",
            len(pdfs), pasta, tipo_codigo or "—", lote, intervalo_seg,
        )

        for i in range(0, len(pdfs), lote):
            if self._stop.is_set():
                return
            chunk = pdfs[i : i + lote]
            db: Session = SessionLocal()
            try:
                for pdf in chunk:
                    if self._stop.is_set():
                        return
                    self._processar_um(db, pdf, tipo_codigo=tipo_codigo)
            finally:
                db.close()
            # Aguarda intervalo antes do próximo lote (se houver mais pdfs)
            if i + lote < len(pdfs) and intervalo_seg > 0:
                self._stop.wait(intervalo_seg)

    def _notificar_ignorado(
        self,
        db: Session,
        pdf: Path,
        *,
        motivo: str,
        layout: str | None = None,
        tipo_codigo: str | None = None,
    ) -> None:
        try:
            notificacoes_service.registrar(
                db,
                arquivo=pdf.name,
                motivo=motivo,
                layout=layout,
                tipo_codigo=tipo_codigo,
                pasta=str(pdf.parent),
            )
        except Exception as e:
            log.error("FULL: não foi possível registrar notificação: %s", e)

    def _processar_um(self, db: Session, pdf: Path, *, tipo_codigo: str | None) -> None:
        senha_pdf = pdf_service.ler_senha_arquivo_auxiliar(pdf)
        try:
            dados = pdf_service.extrair_dados(
                pdf,
                usar_ocr=settings.ocr_enabled,
                senha=senha_pdf,
            )
        except Exception as e:
            log.error("FULL: falha extraindo %s: %s", pdf.name, e)
            self._notificar_ignorado(
                db, pdf, motivo=f"Erro ao ler PDF: {e}", tipo_codigo=tipo_codigo
            )
            return

        if dados.avisos:
            log.warning(
                "FULL: %s layout=%s — %s",
                pdf.name, dados.layout, "; ".join(dados.avisos),
            )
        if not dados.extracao_automatica:
            motivo = "; ".join(dados.avisos) or "Identificação automática indisponível"
            log.warning(
                "FULL: %s não permite identificação automática (layout=%s).",
                pdf.name, dados.layout,
            )
            self._notificar_ignorado(
                db, pdf, motivo=motivo, layout=dados.layout, tipo_codigo=tipo_codigo
            )
            return

        cliente = self._achar_cliente(db, dados)
        if not cliente:
            motivo = (
                f"Cliente não encontrado (CPF={dados.cpf or '—'}, CNPJ={dados.cnpj or '—'}). "
                "Cadastre o cliente com o mesmo documento do PDF."
            )
            log.warning(
                "FULL: cliente não identificado para %s (layout=%s cpf=%s cnpj=%s).",
                pdf.name, dados.layout, dados.cpf, dados.cnpj,
            )
            self._notificar_ignorado(
                db, pdf, motivo=motivo, layout=dados.layout, tipo_codigo=tipo_codigo
            )
            return

        # Tenta achar auto pelo CPF/CNPJ ou pela placa no texto
        auto = self._achar_auto(db, cliente, dados)

        arquivo_por = file_provenance.detectar_arquivo_colocado_por(pdf)

        try:
            envio = envio_service.processar_envio(
                db,
                cliente=cliente,
                caminho_pdf=pdf,
                tipo_envio="FULL",
                tipo_codigo=tipo_codigo,
                auto=auto,
                numero_apolice=dados.numero_apolice,
                nome_arquivo_original=pdf.name,
                pdf_senha=senha_pdf,
                arquivo_colocado_por=arquivo_por,
            )
        except ValueError as e:
            log.warning("FULL: %s", e)
            self._notificar_ignorado(
                db, pdf, motivo=str(e), layout=dados.layout, tipo_codigo=tipo_codigo
            )
            return

        if envio.status == "enviado":
            destino = settings.data_path(settings.processed_folder)
            destino.mkdir(parents=True, exist_ok=True)
            try:
                pdf.rename(destino / pdf.name)
            except Exception as e:
                log.error("FULL: não foi possível mover %s: %s", pdf.name, e)
        else:
            log.error("FULL: envio com erro para %s: %s", pdf.name, envio.erro_msg)
            self._notificar_ignorado(
                db,
                pdf,
                motivo=envio.erro_msg or f"Envio com status {envio.status}",
                layout=dados.layout,
                tipo_codigo=tipo_codigo,
            )

    def _achar_cliente(self, db: Session, dados: pdf_service.DadosPDF) -> models.Cliente | None:
        if dados.cpf:
            c = cliente_crypto.find_by_cpf(db, dados.cpf)
            if c:
                return c
        if dados.cnpj:
            c = cliente_crypto.find_by_cnpj(db, dados.cnpj)
            if c:
                return c
        return None

    def _achar_auto(
        self, db: Session, cliente: models.Cliente, dados: pdf_service.DadosPDF
    ) -> models.Auto | None:
        # Heurística: se houver placa no texto e bater com algum auto do cliente, usa.
        autos = (
            db.query(models.Auto)
            .filter(models.Auto.cliente_id == cliente.id, models.Auto.ativo == True)  # noqa: E712
            .all()
        )
        if not autos:
            return None
        texto = (dados.texto_completo or "").upper()
        for a in autos:
            placa_norm = (a.placa or "").upper().replace("-", "").replace(" ", "")
            if placa_norm and placa_norm in texto.replace("-", "").replace(" ", ""):
                return a
        # Se só tem 1 auto, devolve esse
        if len(autos) == 1:
            return autos[0]
        return None


watcher_global = FullWatcher()
