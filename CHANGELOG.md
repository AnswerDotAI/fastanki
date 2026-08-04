# Release notes

<!-- do not remove -->

## 0.0.6

### New Features

- Vendor Anki protos as serialized descriptors in a private pool to avoid clashing with the installed anki wheel ([#14](https://github.com/AnswerDotAI/fastanki/issues/14))


## 0.0.5

### Bugs Squashed

- Fix `del_card` -> `del_note` in skill exports and refresh README outputs ([#13](https://github.com/AnswerDotAI/fastanki/pull/13)), thanks to [@kafkasl](https://github.com/kafkasl)


## 0.0.4

### New Features

- Add media file sync: filename normalization, media db, zip wire format, and the full media sync state machine ([#11](https://github.com/AnswerDotAI/fastanki/issues/11))
- Allow fastanki operations in pyskills sandboxes ([#10](https://github.com/AnswerDotAI/fastanki/issues/10))


## 0.0.3

### New Features

- add pyskills ([#9](https://github.com/AnswerDotAI/fastanki/pull/9)), thanks to [@racheltho](https://github.com/racheltho)
- Rewrite from scratch using pure-python impl and local db schema ([#8](https://github.com/AnswerDotAI/fastanki/issues/8))
- adding cloze support ([#2](https://github.com/AnswerDotAI/fastanki/pull/2)), thanks to [@racheltho](https://github.com/racheltho)

### Bugs Squashed

- Normal sync returns 'No changes' ([#4](https://github.com/AnswerDotAI/fastanki/issues/4))


## 0.0.2

### New Features

- Add default dict, and support full sync ([#1](https://github.com/AnswerDotAI/fastanki/issues/1))


## 0.0.1

- Init release
