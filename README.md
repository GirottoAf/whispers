# Whispers

Aplicativo Windows para transcrever arquivos locais de áudio e vídeo em TXT usando a API da OpenAI.

## Recursos

- seleção pelo menu do Windows ou arrastar e soltar;
- áudio e vídeo nos formatos mais comuns;
- idioma fixo em português brasileiro (`language=pt` na API);
- texto simples com `gpt-transcribe`;
- timestamps por segmento com `whisper-1`;
- arquivos longos convertidos e divididos localmente;
- chave protegida pelo DPAPI do Windows;
- histórico local dos TXTs gerados;
- instalador self-contained para Windows 10/11 x64.

## Como usar

1. Baixe `Whispers-Setup-x64.exe` na página de [Releases](https://github.com/GirottoAf/whispers/releases).
2. Instale e abra o Whispers. Como o instalador inicial não é assinado, o Windows SmartScreen pode exibir um aviso.
3. Cole uma [chave da API OpenAI](https://platform.openai.com/api-keys). A chave precisa ter acesso à API e faturamento configurado.
4. Selecione ou arraste um arquivo, escolha se deseja timestamps e clique em **Transcrever**.
5. O TXT será salvo em `Documentos\Whispers` e aparecerá no histórico do aplicativo.

Cada usuário utiliza a própria chave e é responsável pelo consumo da API. O arquivo é enviado diretamente à OpenAI; não existe servidor intermediário do Whispers. Áudios temporários são apagados ao concluir, falhar ou cancelar.

## Formatos

Áudio: MP3, WAV, M4A, AAC, FLAC, OGG, OPUS e WMA.

Vídeo: MP4, MKV, MOV, AVI, WEBM, MPEG, MPG, WMV e M4V. Apenas a primeira faixa de áudio é transcrita.

## Desenvolvimento

Requisitos no Windows:

- .NET 8 SDK;
- PowerShell;
- Python 3 para verificações de empacotamento e segurança;
- Inno Setup 6 apenas para montar o instalador.

```powershell
pwsh scripts/Get-FFmpeg.ps1
dotnet restore Whispers.sln
dotnet build Whispers.sln -c Release
dotnet run --project tests/Whispers.Checks -c Release
python tests/verify_release_tag.py
python tests/verify_workflow_security.py
dotnet run --project src/Whispers
```

O script baixa uma compilação LGPL imutável do FFmpeg 8.1.2 e valida seu SHA-256. Os executáveis não são versionados no Git.

Para publicar uma versão, crie e envie uma tag `v*`. O GitHub Actions compila, testa, gera o instalador e cria o release:

```powershell
git tag v0.1.0
git push origin v0.1.0
```

## Estrutura

- `src/Whispers`: aplicativo WPF e pipeline de transcrição;
- `tests/Whispers.Checks`: verificações executáveis sem framework de testes;
- `installer`: definição do instalador Inno Setup;
- `scripts`: aquisição verificada do FFmpeg;
- `SPEC.md`: especificação aprovada do produto.

## Licenças

Whispers usa a licença MIT. FFmpeg/FFprobe são distribuídos separadamente sob LGPL 2.1 ou posterior; veja [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
