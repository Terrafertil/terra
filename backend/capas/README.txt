Pasta de CAPA (PDF)
====================

1. Exporte ou guarde o PDF da capa institucional com o nome definido no .env
   (por defeito: capa.pdf).

2. Caminho por defeito: SEMPRE dentro da pasta do backend:
   <pasta_do_projeto>\backend\capas\capa.pdf
   (pastas ./capas e ./backup no .env são relativas a backend\, não ao diretório
   de onde corre o comando.)

   Variáveis: CAPA_FOLDER, CAPA_ARQUIVO_PADRAO, CAPA_ENABLED no backend\.env

3. Se capa.pdf existir e CAPA_ENABLED=true, cada envio (FULL e AVULSO) junta:
   [ páginas da capa ] + [ páginas do PDF da apólice ]
   O ficheiro único é o que vai para backup e anexo de e-mail.

4. Se não houver ficheiro ou ocorrer erro na junção, o sistema envia só o PDF
   original (comportamento anterior).
