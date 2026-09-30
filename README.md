# Confidence booster

Повтор программы из видео «my confidence booster app 🔥»: окно-«монитор» с вашей веб-камерой (LIVE, REC-таймкод,
зелёная рамка вокруг лица, прицел «WAITING…» в углу). Программа **сама монтирует эдиты из вас**: камера всё время
пишется в буфер (последние 20 секунд), и каждые 10–20 секунд из того, что вы только что делали, собирается эдит —
повтор в слоу-мо, WASTED по вашему стоп-кадру, коллаж из ваших моментов, перемотка назад, — с подписью по тому, что
вы делали (ели, отвернулись, улыбнулись…).

## Какие эдиты собираются

| Шаблон | Что это | Жест, который тоже его запускает |
|---|---|---|
| `replay` | ваш момент в замедлении, стоп-кадр с наездом, белая подпись сверху («snack break») | ладонь у рта, улыбка |
| `freeze_wasted` | слоу-мо в серый стоп-кадр, **WASTED**, картинка рассыпается и гаснет | руки на голове, отвернуться |
| `montage` | ваш момент на весь экран + два других момента вставками, подпись по слову («BAD… MFS») | широко открыть рот |
| `rewind` | последние секунды задом наперёд в стиле VHS, потом стоп-кадр и подпись | кулак |
| `countdown` | живой отсчёт THREE → TWO → ONE (только по жесту) | 👍 или ✌ |

Подпись берётся из `captions` в `config.json` по событию, которое было в этот момент (`hand_mouth`, `smile`,
`look_away`…), а если ничего не было — из `generic`. Можно писать по-русски.

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

Параметры: `--source 1` другая камера, `--auto 5` самодельный эдит каждые 5 секунд, `--no-auto` только по жестам,
`--mute` без звука,
`--debug` показывать сработавший триггер, `--hand-conf 0.3` если руки не находятся.

## Свои эдиты — `config.json`

```json
{
  "edits": [
    {"name": "wasted", "effect": "freeze_wasted", "end": 5.0, "trigger_time": 1.4,
     "trigger": ["auto", "hands_head"], "caption": "WASTED", "size": "panel"},
    {"name": "my clip", "file": "videos/my_clip.mp4", "start": "00:05.000", "end": "00:09.000",
     "trigger_time": "00:07.100", "trigger": "point_up", "caption": "BOOM", "size": "large"}
  ],
  "auto_every": [10, 20],
  "captions": {"hand_mouth": ["snack break"], "generic": ["BAD MFS", "main character"]},
  "pre_edit_sound": "sounds/pre_edit.wav",
  "post_edit_sound": "sounds/post_edit.wav",
  "impact_sound": "sounds/impact.wav",
  "pre_edit_duration": 1.0,
  "cooldown": 6
}
```

- `effect` — эдит без файла: из записи — `replay`, `freeze_wasted`, `montage`, `rewind`; из живой камеры —
  `wasted`, `finished`, `countdown`, `zoom`, `glitch`.
- `file` — или любой видеофайл (mp4, mov…), путь относительно `config.json`. Звук клипа играется вместе с ним.
- `sound` — свой звук/музыка на время эдита (для `effect` — единственный способ добавить музыку).
- `start` / `end` — какой кусок клипа играть (`"MM:SS.mmm"` или секунды); для `effect` — просто длительность.
- `trigger_time` — момент удара: вспышка, тряска, звук `impact_sound`, появляется `caption`
  (для `effect` пустой `caption` — надпись эффекта по умолчанию).
- `trigger` — жест или список жестов (ниже); `"auto"` — эдит, который программа запускает сама.
  `size`: `panel` — в углу, `large` — по центру.
- `auto_every` — раз в сколько секунд самодельный эдит (`[10, 20]` — случайно от 10 до 20).
- `captions` — подписи по событиям. Мем-клипы (`file`) с `"trigger": "auto"` тоже попадают в самодельную ротацию.
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
- `autoedit.py` — буфер записи и самодельные эдиты, `effects.py` — эдиты из живой камеры.
- `make_demo_assets.py` — звуки по умолчанию (и тестовые клипы: `python -c "import make_demo_assets as m; m.demo_clips()"`).
- Тесты: `python tests/test_core.py`, `python tests/test_autoedit.py`.
- Без окна, с записью в файл: `python boost.py --source clip.mp4 --headless --record out.mp4 --auto 3 --mute`.
