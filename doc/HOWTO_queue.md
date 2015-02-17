# Управление очередью проигрывания

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
