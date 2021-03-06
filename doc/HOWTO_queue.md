# Управление очередью проигрывания (заказ музыки)

Любой слушатель может заказывать композиции, отправляя jabber-боту команду `queue`.
Эта команда принимает в качестве параметра фрагмент имени исполнителя или заголовка композиции, ей идентификатор или список меток.
Найденная композиция добавляется в конец очереди.
При выборе следующей композиции для проигрывания очередь имеет максимальный приоритет; за ней следует
виртуальный плейлист, затем остальные плейлисты.

Привилегированные пользователи могут добавлять композиции в любом количестве и в любое время.
Обычные пользователи могут добавлять по одной композиции за раз (новую добавить нельзя пока предыдущая не проиграна), и к таким композициям в качестве подмотки добавляется случайная композиция с меткой «queue-jingle», если такие есть (смысл этих ограничений в том, чтобы резвящийся слушатель был очевиден, чтобы его нельзя было принять за дефект программного обеспечения).


## Управление через jabber

    > find дом
    «Песня идущего домой» by Ю-Питер — #6899 ⚖1.00 ♺0
    > queue 6899


## Управление через API

Для постановки дорожки в очередь следует вызвать `track/queue.json`.
Параметры:

- `track` — номер дорожки.
- `token` — ключ для аутентификации.

Пример вызова:

    $ curl 'http://music.tmradio.net/track/queue.json?track=6065&token=secret'
    {
      "success": true
    }

Это идентично выполнению команды `queue -s 6065` в консоли или через jabber.
