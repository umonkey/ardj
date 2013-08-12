Чтобы один исполнитель не играл несколько раз подряд, можно использовать в
плейлисте свойство `artist_delay`.  В качестве значения следует указать
количество других исполнителей, которые должны прозвучать прежде, чем сможет
снова звучать текущий.

Пример плейлиста, в котором один испонитель может звучать не чаще одного раза за
пять песен:

    - name: music
      labels: [music]
      artist_delay: 5