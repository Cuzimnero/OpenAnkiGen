# Local TTS models

Piper voice models are stored here, separated by language:

```text
tts_models/
├── German/de_DE-thorsten-medium.onnx
├── English/en_US-lessac-medium.onnx
└── Spanish/es_ES-davefx-medium.onnx
```

Each voice also has a matching `.onnx.json` configuration file. Missing voices are downloaded once when an audiobook
is requested and are then used entirely offline. Large model files are intentionally excluded from Git.
