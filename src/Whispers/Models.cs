namespace Whispers;

public sealed record TranscriptFile(string FilePath, DateTime ModifiedAtUtc)
{
    public string Name => Path.GetFileName(FilePath);
    public string ModifiedAt => ModifiedAtUtc.ToLocalTime().ToString("dd/MM/yyyy HH:mm");
}

public sealed class AppState
{
    public string? ProtectedApiKey { get; set; }
    public string? OutputDirectory { get; set; }
}

public sealed record MediaInfo(TimeSpan Duration, long Size);
public sealed record AudioChunk(string Path, TimeSpan Start);
public sealed record TranscriptSegment(double Start, double End, string Text);
public sealed record ChunkTranscript(string Text, IReadOnlyList<TranscriptSegment> Segments);
public sealed record WorkflowProgress(string Message, int Completed, int Total, bool IsIndeterminate = false);

public sealed class PreparedMedia(string temporaryDirectory, IReadOnlyList<AudioChunk> chunks) : IDisposable
{
    public IReadOnlyList<AudioChunk> Chunks { get; } = chunks;

    public void Dispose()
    {
        try
        {
            if (Directory.Exists(temporaryDirectory))
                Directory.Delete(temporaryDirectory, true);
        }
        catch (IOException)
        {
            // O sistema operacional também limpa a pasta temporária posteriormente.
        }
        catch (UnauthorizedAccessException)
        {
        }
    }
}

public sealed class TranscriptionException(string message, int? statusCode = null) : Exception(message)
{
    public int? StatusCode { get; } = statusCode;
}
