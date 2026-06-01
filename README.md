# GPT Realtime Voice Bot

OpenAI Realtime API と WebRTC を使った Streamlit ボイスボットです。

## Setup

```bash
export OPENAI_API_KEY="sk-..."
uv run streamlit run main.py
```

Streamlit Cloud などで使う場合は、Secrets に `OPENAI_API_KEY` を設定してください。

## Notes

- ブラウザでマイク許可が必要です。
- 音声会話は WebRTC で接続します。
- API キー本体はサーバー側だけで使い、ブラウザには短命の client secret だけを渡します。
