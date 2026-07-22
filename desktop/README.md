# Aplicativo Windows Terra Fértil

Cliente Windows que abre `http://192.168.0.130:5173/` em uma janela WebView2 própria.
Ele inicia maximizado, com os controles nativos de minimizar, restaurar/maximizar e
fechar, e usa o ícone da Terra Fértil na janela e no executável.

## Gerar

O SDK do .NET 8 é necessário somente na máquina que gera o executável:

```powershell
cd desktop
.\publicar.ps1
```

O resultado fica em `desktop/publish/`. Distribua todo o conteúdo dessa pasta. O
programa é autocontido e não exige o SDK do .NET nos computadores clientes.

O WebView2 Runtime precisa existir no PC. Ele acompanha o Windows 11 e a maioria das
instalações atuais do Windows 10. Se necessário, instale o Evergreen Runtime oficial.

Para trocar o endereço depois da publicação, edite `appsettings.json` ao lado do
executável e reinicie o programa.
