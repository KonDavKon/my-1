# Confidence booster

Повтор программы из видео «my confidence booster app 🔥»: окно-«монитор» с вашей веб-камерой (LIVE, REC-таймкод,
зелёная рамка вокруг лица, прицел «WAITING…» в углу). Когда вы делаете жест или выражение лица, программа проигрывает
«эдит» — клип с музыкой, вспышкой и надписью в момент удара (как «WASTED», «FINISHED» в оригинале).

## Запуск (Windows)

Нужны Python 3.10+ и Git. Если `python --version` ничего не печатает — используйте `py`.

```powershell
git clone https://github.com/KonDavKon/my-1.git
cd my-1
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe boost.py
```

Или двойной клик по `start.bat`. При первом запуске скачиваются модели MediaPipe (~12 МБ) и создаются демо-клипы
и звуки, так что программа работает сразу.

Клавиши: `q`/`Esc` — выход, `1`–`9` — запустить эдит по номеру, `пробел` — случайный эдит, `f` — полный экран.

Параметры: `--source 1` другая камера, `--auto 5` эдит каждые 5 секунд без жестов, `--mute` без звука,
`--debug` показывать сработавший триггер, `--hand-conf 0.3` если руки не находятся.

## Свои эдиты — `config.json`

```json
{
  "edits": [
    {"name": "wasted", "file": "videos/wasted.mp4", "start": "00:00.000", "end": "00:04.000",
     "trigger_time": "00:02.100", "trigger": "hands_head", "caption": "WASTED", "size": "panel"}
  ],
  "pre_edit_sound": "sounds/pre_edit.wav",
  "post_edit_sound": "sounds/post_edit.wav",
  "impact_sound": "sounds/impact.wav",
  "pre_edit_duration": 1.0,
  "cooldown": 6
}
```

- `file` — любой видеофайл (mp4, mov…), путь относительно `config.json`. Звук клипа играется вместе с ним.
- `start` / `end` — какой кусок клипа играть (`"MM:SS.mmm"` или секунды).
- `trigger_time` — момент удара внутри клипа: вспышка, тряска, звук `impact_sound`, появляется `caption`.
- `trigger` — жест или список жестов (ниже). `size`: `panel` — в углу, `large` — по центру.
- `pre_edit_sound` играет за `pre_edit_duration` секунд до клипа («INCOMING»), `post_edit_sound` — после.
- `cooldown` — пауза после эдита, можно задать и для отдельного эдита.

Папки `videos/` и `sounds/` не попадают в git: кладите туда свои клипы и звуки.

## Триггеры

| Триггер | Что сделать |
|---|---|
| `smile` | широко улыбнуться |
| `mouth_open` | широко открыть рот |
| `eyes_closed` | закрыть глаза (0,7 с) |
| `eyebrows_up` | поднять брови |
| `look_away` | отвернуться (0,5 с) |
| `face_lost` | уйти из кадра (1 с) |
| `fist` | кулак |
| `thumbs_up` | большой палец вверх |
| `point_up` | указательный палец вверх |
| `peace` | «виктория» ✌ |
| `shaka` | большой палец и мизинец 🤙 |
| `open_palm` | открытая ладонь |
| `hand_mouth` | ладонь у рта |
| `hands_head` | обе руки на голове |
| `hands_up` | обе руки над головой |

Жест должен держаться ~0,25 с. Один и тот же жест срабатывает снова, только если его «отпустить».

## Как устроено

- `boost.py` — камера, MediaPipe (руки + лицо), главный цикл, окно.
- `triggers.py` — жесты и мимика на numpy, `player.py` — этапы эдита (ожидание → INCOMING → клип → конец),
  `hud.py` — отрисовка, `config.py` — чтение конфига, `audio.py` — звук (pygame; звук клипа вырезается ffmpeg в `.cache/`).
- `make_demo_assets.py` — демо-клипы и звуки.
- Тесты: `python tests/test_core.py`.
- Без окна, с записью в файл: `python boost.py --source clip.mp4 --headless --record out.mp4 --auto 3 --mute`.
