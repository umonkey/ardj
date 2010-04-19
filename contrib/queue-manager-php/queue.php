<?php

header('content-type: text/html; charset=utf-8');
ini_set('display_errors', 1);

chdir(dirname(__FILE__));

try {
	$db = new PDO('sqlite:ardj.sqlite');
	$db->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);

	if ('POST' == $_SERVER['REQUEST_METHOD']) {
		$db->beginTransaction();
		$sth = $db->prepare('UPDATE tracks SET queue = ? WHERE playlist = ? AND name = ?');
		foreach ((array)$_POST['track'] as $k => $v) {
			list($playlist, $track) = explode(DIRECTORY_SEPARATOR, $k, 2);
			$sth->execute($params = array(intval($v), $playlist, $track));
		}
		$db->commit();
	}

	$sth = $db->prepare('SELECT playlist, name, queue FROM tracks ORDER BY playlist, name');
	$sth->execute();

	print "<html>\n";
	print "<head>\n<title>ardj queue</title>\n";
	print "<link rel='stylesheet' type='text/css' href='queue.css'/>\n";
	print "</head>\n";
	print "<body>\n<h1>queue manager for <a href='http://ardj.googlecode.com/' target='_blank'>ardj</a></h1>\n";
	print "<form method='post'>\n";
	print "<table>\n";
	print "<thead><tr><th>Playlist</th><th>Track</th><th>Priority</th></tr></thead>\n";
	print "<tbody>\n";
	foreach ($sth->fetchAll(PDO::FETCH_ASSOC) as $row) {
		$track_id = htmlspecialchars($row['playlist'] . DIRECTORY_SEPARATOR . $row['name'], ENT_QUOTES);
		printf("<tr><td>%s</td><td>%s</td><td><input type='text' name='track[%s]' value='%u'/></td></tr>\n", htmlspecialchars($row['playlist']), htmlspecialchars($row['name']), $track_id, $row['queue']);
	}
	print "</tbody>\n</table>\n";
	print "<div><button type='submit'>Submit</button></div>\n";
	print "</form>";
	print "</body>\n</html>\n";
} catch (Exception $e) {
	var_dump($e->getMessage());
}
