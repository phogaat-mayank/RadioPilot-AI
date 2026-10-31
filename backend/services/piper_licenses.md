# Piper TTS & Voice Models — Official License Documentation

RadioPilot AI integrates **Piper**, a free, local neural text-to-speech system developed by the open-source community (Rhasspy). Piper operates 100% on-device using ONNX Runtime with zero external API calls, zero telemetry, and zero subscription costs.

---

## 1. Piper Engine License

- **Software**: Piper TTS (`piper-tts` / `piper-phonemize`)
- **Repository**: [https://github.com/rhasspy/piper](https://github.com/rhasspy/piper)
- **Author**: Michael Hansen (@synesthesiam)
- **License**: **MIT License**
- **Terms**: Free for both non-commercial and commercial software development, modification, and distribution.

---

## 2. Integrated Voice Models & Attribution

RadioPilot AI uses real, verified ONNX models from the official [Rhasspy Piper Voices](https://huggingface.co/rhasspy/piper-voices) repository:

| Model ID | Language | Gender | Dataset & Origin | License |
|---|---|---|---|---|
| **`hi_IN-priyamvada-medium`** | Hindi (`hi_IN`) | Female | AI4Bharat IndicNLP Corpus (Trained by PravalX) | **CC BY-NC-SA 4.0** |
| **`hi_IN-pratham-medium`** | Hindi (`hi_IN`) | Male | AI4Bharat IndicNLP Corpus (Trained by PravalX) | **CC BY-NC-SA 4.0** |
| **`en_US-lessac-medium`** | English (`en_US`) | Female | University of Edinburgh CSTR Lessac Corpus (Blizzard Challenge 2013) | **CSTR Research / Non-Commercial** |
| **`en_US-ryan-medium`** | English (`en_US`) | Male | RyanSpeech Corpus | **CC BY-NC-SA 4.0** |

---

## 3. Summary of Terms & Conditions

1. **Non-Commercial & Research Use**: All four bundled models permit free, self-hosted deployment on personal, educational, and non-commercial radio broadcasting servers.
2. **Attribution**:
   - Hindi models trained on the AI4Bharat IndicNLP dataset.
   - English Lessac model created by the Centre for Speech Technology Research (CSTR), University of Edinburgh.
   - English Ryan model created using the RyanSpeech dataset.
3. **No External Network Dependencies**: All model weights (`.onnx`) and phoneme mappings (`.onnx.json`) execute locally in CPU memory.
