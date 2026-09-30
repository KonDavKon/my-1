# Confidence booster

Повтор программы из видео «my confidence booster app 🔥»: окно-«монитор» с вашей веб-камерой (LIVE, REC-таймкод,
зелёная рамка вокруг лица, прицел «WAITING…» в углу). Когда вы делаете жест или выражение лица, программа проигрывает
«эдит» со вспышкой и надписью в момент удара (как «WASTED», «FINISHED» в оригинале).

Эдиты бывают двух видов:
- **живые** (`effect`) — делаются прямо из вашей камеры, файлы не нужны;
- **видеоклипы** (`file`) — любой ваш ролик со своим звуком.

## Что работает сразу

| Жест | Эдит | Что происходит |
|---|---|---|
| обе руки на голове | `wasted` | медленный зум, картинка сереет, в момент удара красное **WASTED** |
| широко открыть рот | `finished` | стоп-кадр в красном свете, крупно **FINISHED** |
| палец вверх 👍 или ✌ | `countdown` | **THREE → TWO → ONE** с наездом камеры на каждое слово |
| кулак | `zoom` | резкий наезд на лицо, холодный цвет, **LOCKED IN** |
| широкая улыбка | `glitch` | цифровой глитч, в момент удара **AURA +1000** |

Клавиши `1`–`5` запускают эти эдиты без жестов.

## Запуск (Windows)

Нужны Python 3.10+ и Git. Если `python --version` ничего не печатает — используйте `py`.

```powershell
git clone https://github.com/KonDavKon/my-1.git
cd my-1
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe boost.py
```

Или двойной клик по `start.bat`. При первом запуске скачиваются модели MediaPipe (~12 МБ, при обрыве связи загрузка
докачивается с того же места) и создаются звуки.

Клавиши: `q`/`Esc` — выход, `1`–`9` — запустить эдит по номеру, `пробел` — случайный эдит, `f` — полный экран.

Параметры: `--source 1` другая камера, `--auto 5` эдит каждые 5 секунд без жестов, `--mute` без звука,
`--debug` показывать сработавший триггер, `--hand-conf 0.3` если руки не находятся.

## Свои эдиты — `config.json`

```json
{
  "edits": [
    {"name": "wasted", "effect": "wasted", "start": "00:00.000", "end": "00:03.500",
     "trigger_time": "00:01.500", "trigger": "hands_head", "caption": "WASTED", "size": "panel"},
    {"name": "my clip", "file": "videos/my_clip.mp4", "start": "00:05.000", "end": "00:09.000",
     "trigger_time": "00:07.100", "trigger": "point_up", "caption": "BOOM", "size": "large"}
  ],
  "pre_edit_sound": "sounds/pre_edit.wav",
  "post_edit_sound": "sounds/post_edit.wav",
  "impact_sound": "sounds/impact.wav",
  "pre_edit_duration": 1.0,
  "cooldown": 6
}
```

- `effect` — живой эдит из камеры: `wasted`, `finished`, `countdown`, `zoom`, `glitch`.
- `file` — или любой видеофайл (mp4, mov…), путь относительно `config.json`. Звук клипа играется вместе с ним.
- `sound` — свой звук/музыка на время эдита (для `effect` — единственный способ добавить музыку).
- `start` / `end` — какой кусок клипа играть (`"MM:SS.mmm"` или секунды); для `effect` — просто длительность.
- `trigger_time` — момент удара: вспышка, тряска, звук `impact_sound`, появляется `caption`
  (для `effect` пустой `caption` — надпись эффекта по умолчанию).
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
- `effects.py` — живые эдиты из камеры.
- `make_demo_assets.py` — звуки по умолчанию (и тестовые клипы: `python -c "import make_demo_assets as m; m.demo_clips()"`).
- Тесты: `python tests/test_core.py`.
- Без окна, с записью в файл: `python boost.py --source clip.mp4 --headless --record out.mp4 --auto 3 --mute`.
