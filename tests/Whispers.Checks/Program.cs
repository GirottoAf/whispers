using System.Net;
using System.Net.Http;
using System.Net.Http.Headers;
using Whispers;

var temporaryDirectory = Path.Combine(Path.GetTempPath(), "WhispersChecks", Guid.NewGuid().ToString("N"));
Directory.CreateDirectory(temporaryDirectory);

try
{
    Check(OutputFile.FormatTimestamp(3723.9) == "01:02:03", "formatação de timestamp");
    var firstOutput = OutputFile.CreateUniquePath("reuniao.mp4", true, temporaryDirectory);
    await File.WriteAllTextAsync(firstOutput, "existente");
    var secondOutput = OutputFile.CreateUniquePath("reuniao.mp4", true, temporaryDirectory);
    Check(Path.GetFileName(secondOutput) == "reuniao_timestamps (2).txt", "nome sem sobrescrita");

    var selectedOutput = Path.Combine(temporaryDirectory, "destino-escolhido");
    Directory.CreateDirectory(selectedOutput);
    var selectedOutputPath = OutputFile.CreateUniquePath("entrevista.m4a", false, selectedOutput);
    Check(Path.GetDirectoryName(selectedOutputPath) == selectedOutput, "pasta escolhida para saída");

    var store = new AppStateStore(Path.Combine(temporaryDirectory, "state"));
    store.SetApiKey("sk-test-secret");
    store.SetOutputDirectory(selectedOutput);
    store.AddHistory(new HistoryEntry(Guid.NewGuid(), "entrada.mp3", "saida.txt", DateTime.UtcNow, false));
    var reloaded = new AppStateStore(Path.Combine(temporaryDirectory, "state"));
    Check(reloaded.GetApiKey() == "sk-test-secret", "DPAPI");
    Check(reloaded.State.OutputDirectory == Path.GetFullPath(selectedOutput), "pasta escolhida persistida");
    Check(reloaded.State.History.Count == 1, "histórico");
    var stateText = await File.ReadAllTextAsync(Path.Combine(temporaryDirectory, "state", "app-state.json"));
    Check(!stateText.Contains("sk-test-secret", StringComparison.Ordinal), "chave não pode ficar em texto puro");

    var nullHistoryDirectory = Path.Combine(temporaryDirectory, "null-history");
    Directory.CreateDirectory(nullHistoryDirectory);
    await File.WriteAllTextAsync(Path.Combine(nullHistoryDirectory, "app-state.json"), "{\"History\":null}");
    var nullHistoryStore = new AppStateStore(nullHistoryDirectory);
    nullHistoryStore.AddHistory(new HistoryEntry(Guid.NewGuid(), "entrada.mp3", "saida.txt", DateTime.UtcNow, false));
    Check(nullHistoryStore.State.History.Count == 1, "histórico nulo deve ser recuperado");

    var audioPath = Path.Combine(temporaryDirectory, "chunk.mp3");
    await File.WriteAllBytesAsync(audioPath, [1, 2, 3]);
    string? sentBody = null;
    string? sentLanguage = null;
    AuthenticationHeaderValue? authorization = null;
    using (var client = new OpenAiTranscriptionClient("sk-test", new FakeHandler(async request =>
    {
        authorization = request.Headers.Authorization;
        sentLanguage = await ((MultipartFormDataContent)request.Content!).First(part =>
            part.Headers.ContentDisposition?.Name?.Trim('"') == "language").ReadAsStringAsync();
        sentBody = await request.Content!.ReadAsStringAsync();
        return Json(HttpStatusCode.OK, "{\"text\":\"Olá\"}");
    })))
    {
        var result = await client.TranscribeAsync(audioPath, false, CancellationToken.None);
        Check(result.Text == "Olá", "resposta simples");
    }
    Check(authorization?.Scheme == "Bearer" && authorization.Parameter == "sk-test", "autorização bearer");
    Check(sentBody?.Contains("gpt-transcribe", StringComparison.Ordinal) == true, "modelo sem timestamps");
    Check(sentLanguage == "pt", "idioma português fixo");

    using (var client = new OpenAiTranscriptionClient("sk-test", new FakeHandler(_ => Task.FromResult(
        Json(HttpStatusCode.OK, "{\"text\":\"Oi\",\"segments\":[{\"start\":1.2,\"end\":2.0,\"text\":\"Oi\"}]}")))))
    {
        var result = await client.TranscribeAsync(audioPath, true, CancellationToken.None);
        Check(result.Segments.Count == 1 && result.Segments[0].Start == 1.2, "segmentos");
    }

    var attempts = 0;
    using (var client = new OpenAiTranscriptionClient("sk-test", new FakeHandler(_ =>
    {
        attempts++;
        var response = attempts < 3
            ? Json(HttpStatusCode.InternalServerError, "{}")
            : Json(HttpStatusCode.OK, "{\"text\":\"recuperado\"}");
        if (attempts < 3)
            response.Headers.RetryAfter = new RetryConditionHeaderValue(TimeSpan.Zero);
        return Task.FromResult(response);
    })))
    {
        var result = await client.TranscribeAsync(audioPath, false, CancellationToken.None);
        Check(result.Text == "recuperado" && attempts == 3, "retry transitório");
    }

    using (var client = new OpenAiTranscriptionClient("sk-test", new FakeHandler(_ => Task.FromResult(
        Json(HttpStatusCode.Unauthorized, "{}")))))
    {
        try
        {
            await client.TranscribeAsync(audioPath, false, CancellationToken.None);
            throw new Exception("erro 401 não detectado");
        }
        catch (TranscriptionException ex)
        {
            Check(ex.StatusCode == 401, "erro de chave");
        }
    }

    using (var client = new OpenAiTranscriptionClient("sk-test", new FakeHandler(_ => Task.FromResult(
        Json(HttpStatusCode.OK, "{\"text\":\"Oi\",\"segments\":{}}")))))
    {
        try
        {
            await client.TranscribeAsync(audioPath, true, CancellationToken.None);
            throw new Exception("resposta inválida não detectada");
        }
        catch (TranscriptionException)
        {
        }
    }

    Console.WriteLine("Whispers checks: OK");
}
finally
{
    try { Directory.Delete(temporaryDirectory, true); } catch { }
}

static HttpResponseMessage Json(HttpStatusCode status, string content) =>
    new(status) { Content = new StringContent(content, System.Text.Encoding.UTF8, "application/json") };

static void Check(bool condition, string name)
{
    if (!condition)
        throw new Exception($"Falhou: {name}");
}

sealed class FakeHandler(Func<HttpRequestMessage, Task<HttpResponseMessage>> responder) : HttpMessageHandler
{
    protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken) =>
        responder(request);
}
