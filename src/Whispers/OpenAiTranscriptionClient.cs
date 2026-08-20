using System.Net;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Text.Json;

namespace Whispers;

public sealed class OpenAiTranscriptionClient : IDisposable
{
    private static readonly Uri Endpoint = new("https://api.openai.com/v1/audio/transcriptions");
    private readonly HttpClient _httpClient;

    public OpenAiTranscriptionClient(string apiKey, HttpMessageHandler? handler = null)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(apiKey);
        _httpClient = handler is null ? new HttpClient() : new HttpClient(handler);
        _httpClient.Timeout = TimeSpan.FromMinutes(30);
        _httpClient.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", apiKey.Trim());
    }

    public async Task<ChunkTranscript> TranscribeAsync(
        string audioPath,
        bool timestamps,
        CancellationToken cancellationToken)
    {
        for (var attempt = 1; attempt <= 3; attempt++)
        {
            try
            {
                using var form = new MultipartFormDataContent();
                await using var stream = File.OpenRead(audioPath);
                using var audio = new StreamContent(stream);
                audio.Headers.ContentType = new MediaTypeHeaderValue("audio/mpeg");
                form.Add(audio, "file", Path.GetFileName(audioPath));
                form.Add(new StringContent(timestamps ? "whisper-1" : "gpt-transcribe"), "model");
                form.Add(new StringContent("pt"), "language");
                if (timestamps)
                {
                    form.Add(new StringContent("verbose_json"), "response_format");
                    form.Add(new StringContent("segment"), "timestamp_granularities[]");
                }

                using var response = await _httpClient.PostAsync(Endpoint, form, cancellationToken);
                var body = await response.Content.ReadAsStringAsync(cancellationToken);
                if (response.IsSuccessStatusCode)
                    return Parse(body, timestamps);

                if (IsTransient(response.StatusCode) && attempt < 3)
                {
                    await Task.Delay(GetRetryDelay(response, attempt), cancellationToken);
                    continue;
                }

                throw CreateApiException(response.StatusCode);
            }
            catch (HttpRequestException) when (attempt < 3)
            {
                await Task.Delay(TimeSpan.FromSeconds(attempt), cancellationToken);
            }
            catch (HttpRequestException ex)
            {
                throw new TranscriptionException("Não foi possível conectar à OpenAI. Verifique sua internet.", null) { Source = ex.Source };
            }
        }

        throw new TranscriptionException("A transcrição falhou após três tentativas.");
    }

    public void Dispose() => _httpClient.Dispose();

    private static ChunkTranscript Parse(string body, bool timestamps)
    {
        try
        {
            using var json = JsonDocument.Parse(body);
            var root = json.RootElement;
            var text = root.TryGetProperty("text", out var textElement) ? textElement.GetString() ?? "" : "";
            var segments = new List<TranscriptSegment>();
            if (root.TryGetProperty("segments", out var segmentElements))
            {
                foreach (var segment in segmentElements.EnumerateArray())
                {
                    segments.Add(new TranscriptSegment(
                        segment.GetProperty("start").GetDouble(),
                        segment.GetProperty("end").GetDouble(),
                        segment.GetProperty("text").GetString() ?? ""));
                }
            }

            if (string.IsNullOrWhiteSpace(text) || timestamps && segments.Count == 0)
                throw new JsonException();
            return new ChunkTranscript(text, segments);
        }
        catch (Exception ex) when (ex is JsonException or InvalidOperationException or KeyNotFoundException or FormatException)
        {
            throw new TranscriptionException("A OpenAI retornou uma resposta de transcrição inválida.") { Source = ex.Source };
        }
    }

    private static bool IsTransient(HttpStatusCode statusCode) =>
        statusCode == HttpStatusCode.TooManyRequests || (int)statusCode >= 500;

    private static TimeSpan GetRetryDelay(HttpResponseMessage response, int attempt)
    {
        var delay = response.Headers.RetryAfter?.Delta;
        if (delay is null && response.Headers.RetryAfter?.Date is { } date)
            delay = date - DateTimeOffset.UtcNow;
        return delay.HasValue && delay.Value > TimeSpan.Zero && delay.Value < TimeSpan.FromMinutes(2)
            ? delay.Value : TimeSpan.FromSeconds(attempt);
    }

    private static TranscriptionException CreateApiException(HttpStatusCode statusCode)
    {
        var message = statusCode switch
        {
            HttpStatusCode.Unauthorized => "Chave da API inválida. Substitua-a nas configurações.",
            HttpStatusCode.Forbidden => "A chave não possui permissão para usar o modelo de transcrição.",
            HttpStatusCode.TooManyRequests => "Limite de uso atingido ou saldo insuficiente na conta OpenAI.",
            HttpStatusCode.RequestEntityTooLarge => "A OpenAI recusou o áudio porque ele excede o limite permitido.",
            HttpStatusCode.BadRequest => "A OpenAI recusou o áudio ou os parâmetros enviados.",
            _ => $"A OpenAI retornou um erro temporário ({(int)statusCode})."
        };
        return new TranscriptionException(message, (int)statusCode);
    }
}
