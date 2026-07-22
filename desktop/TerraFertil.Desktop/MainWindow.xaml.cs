using System.Diagnostics;
using System.IO;
using System.Net.Http;
using System.Text.Json;
using System.Windows;
using Microsoft.Web.WebView2.Core;

namespace TerraFertil.Desktop;

public partial class MainWindow : Window
{
    private static readonly HttpClient Http = new() { Timeout = TimeSpan.FromSeconds(8) };
    private readonly Uri _serverUri;

    public MainWindow()
    {
        InitializeComponent();
        _serverUri = LoadServerUri();
        Loaded += MainWindow_Loaded;
    }

    private static Uri LoadServerUri()
    {
        const string defaultUrl = "http://192.168.0.130:5173/";
        var configPath = Path.Combine(AppContext.BaseDirectory, "appsettings.json");
        try
        {
            if (File.Exists(configPath))
            {
                using var document = JsonDocument.Parse(File.ReadAllText(configPath));
                var configured = document.RootElement.GetProperty("ServerUrl").GetString();
                if (Uri.TryCreate(configured, UriKind.Absolute, out var uri) &&
                    (uri.Scheme == Uri.UriSchemeHttp || uri.Scheme == Uri.UriSchemeHttps))
                    return EnsureTrailingSlash(uri);
            }
        }
        catch (Exception) { }
        return new Uri(defaultUrl);
    }

    private static Uri EnsureTrailingSlash(Uri uri) =>
        uri.AbsolutePath.EndsWith('/') ? uri : new Uri(uri.AbsoluteUri + "/");

    private async void MainWindow_Loaded(object sender, RoutedEventArgs e) => await ConnectAsync();

    private async Task ConnectAsync()
    {
        ShowLoading();
        try
        {
            using var response = await Http.GetAsync(_serverUri);
            response.EnsureSuccessStatusCode();
            var userDataFolder = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "TerraFertil", "WebView2");
            var environment = await CoreWebView2Environment.CreateAsync(userDataFolder: userDataFolder);
            await Browser.EnsureCoreWebView2Async(environment);
            ConfigureBrowser();
            Browser.Source = _serverUri;
            Browser.Visibility = Visibility.Visible;
            LoadingPanel.Visibility = Visibility.Collapsed;
        }
        catch (Exception ex)
        {
            ShowOffline($"Não foi possível acessar {_serverUri}\n\n{FriendlyError(ex)}");
        }
    }

    private void ConfigureBrowser()
    {
        var settings = Browser.CoreWebView2.Settings;
        settings.AreDevToolsEnabled = false;
        settings.AreDefaultContextMenusEnabled = false;
        settings.IsStatusBarEnabled = false;
        settings.IsZoomControlEnabled = true;
        Browser.CoreWebView2.NavigationStarting -= NavigationStarting;
        Browser.CoreWebView2.NavigationStarting += NavigationStarting;
        Browser.CoreWebView2.NewWindowRequested -= NewWindowRequested;
        Browser.CoreWebView2.NewWindowRequested += NewWindowRequested;
        Browser.CoreWebView2.ProcessFailed -= ProcessFailed;
        Browser.CoreWebView2.ProcessFailed += ProcessFailed;
    }

    private void NavigationStarting(object? sender, CoreWebView2NavigationStartingEventArgs e)
    {
        if (!Uri.TryCreate(e.Uri, UriKind.Absolute, out var destination) || !IsAllowed(destination))
        {
            e.Cancel = true;
            OpenInDefaultBrowser(e.Uri);
        }
    }

    private void NewWindowRequested(object? sender, CoreWebView2NewWindowRequestedEventArgs e)
    {
        e.Handled = true;
        OpenInDefaultBrowser(e.Uri);
    }

    private void ProcessFailed(object? sender, CoreWebView2ProcessFailedEventArgs e) =>
        ShowOffline("O componente de exibição foi interrompido. Tente conectar novamente.");

    private bool IsAllowed(Uri uri) => uri.Scheme == _serverUri.Scheme &&
        uri.Host.Equals(_serverUri.Host, StringComparison.OrdinalIgnoreCase) && uri.Port == _serverUri.Port;

    private static void OpenInDefaultBrowser(string address)
    {
        if (!Uri.TryCreate(address, UriKind.Absolute, out var uri) ||
            (uri.Scheme != Uri.UriSchemeHttp && uri.Scheme != Uri.UriSchemeHttps)) return;
        Process.Start(new ProcessStartInfo(uri.AbsoluteUri) { UseShellExecute = true });
    }

    private static string FriendlyError(Exception ex) => ex switch
    {
        HttpRequestException => "Verifique se o frontend está iniciado no servidor e se a porta 5173 está liberada no firewall.",
        TaskCanceledException => "O servidor demorou demais para responder.",
        _ => "Verifique a conexão de rede e tente novamente."
    };

    private void ShowLoading()
    {
        OfflinePanel.Visibility = Visibility.Collapsed;
        Browser.Visibility = Visibility.Collapsed;
        LoadingPanel.Visibility = Visibility.Visible;
    }

    private void ShowOffline(string message)
    {
        Browser.Visibility = Visibility.Collapsed;
        LoadingPanel.Visibility = Visibility.Collapsed;
        OfflineMessage.Text = message;
        OfflinePanel.Visibility = Visibility.Visible;
    }

    private async void Retry_Click(object sender, RoutedEventArgs e) => await ConnectAsync();
}
