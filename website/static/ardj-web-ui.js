ardj = {
	init: function () {
		String.prototype.format = ardj.format_string;

		if (ardj.get_token())
			$("body").addClass("authenticated");
		else
			$("body").addClass("anonymous");

		$("#searchform input:first").focus();

		$("#searchform form").submit(function () {
			if ($("#searchform form input")[0].value) {
				ardj.search_scope();
			} else {
				ardj.recent_scope();
			}
			return false;
		});

		$(".eg").click(ardj.sample_search);

		$(".login").click(ardj.show_login_form);
		$(".tags").click(ardj.show_tags);

		$("#loginform form").submit(ardj.submit_login_form);

		ardj.recent_scope();		
	},

	search_scope: function() {
		var searchForm = $("#searchform form");
		$.ajax({
				url: $(searchForm).attr("action"),
				dataType: "json",
				data: $(searchForm).serialize(),
				success: ardj.search_complete
		});
	},

	recent_scope: function() {
		$.ajax({
			url: "/track/recent.json",
			dataType: "json",
			success: ardj.search_complete
		});
	},

	sample_search: function () {
		$("#searchform input")
			.val($(this).text())
			.focus();
	},

	show_login_form: function () {
		$("#loginform").show();
		return false;
	},

	submit_login_form: function () {
		$.ajax({
			url: $(this).attr("action"),
			type: "POST",
			data: $(this).serialize(),
			dataType: "json",
			success: function (data) {
				if (data.status == "ok") {
					var token = prompt("Please enter the token:", "");
					ardj.set_token(token);
				}
			}
		});
		return false;
	},

	show_tags: function () {
		$.ajax({
			url: "/api/tag/cloud.json",
			dataType: "json",
			success: ardj.render_tag_cloud
		});
		return false;
	},

	render_tag_cloud: function (data) {
		var html = "<h2>Top tags:</h2><ul class='tagcloud'>";

		data.tags.forEach(function (x) {
			html += "<li><span>{0}</span> ({1})</li>".format(x);
		});

		$("#searchresult").html(html).find("span").click(function () {
			$("#searchform input").val("@" + $(this).text()).focus();
		});
	},

	/**
	 * Форматирование результатов запроса.
	 *
	 * Отформатированный результат отправляется в #searchresult.
	 *
	 * @param object data Описание результата.  Массив tracks должен содержать
	 * информацию о дорожках.
	 */
	search_complete: function (data) {
		var html = "";
		var token = ardj.get_token();
		if (data.scope == "search")
			html += "<h2>Search results:</h2>";
		else if (data.scope == "recent")
			html += "<h2>Recently played tracks</h2>";

		if (data.tracks.length) {
			html += "<table><tbody>";

			data.tracks.forEach(function (track) {
				html += ardj.render_track({'track': track, 'token': token});
			});

			html += "</tbody></table>";
		} else {
			html += "<p>Nothing.</p>";
		}

		html = $("#searchresult").html(html);
		ardj.update_events(html);
		$("#searchform input:first").focus();
	},

	update_events: function(html) {
		html.find("a").attr("target", "_blank");
		html.find(".queue a").click(ardj.queue_track);
		html.find(".rocks a, .sucks a").click(ardj.vote);
	},

	format_length: function(length) {
		var min = parseInt(length/60);
		var sec = parseInt(length - min*60);
		var minStr = min + '';
		var secStr = sec + '';
		while(minStr.length < 2) minStr = "0" + minStr;
		while(secStr.length < 2) secStr = "0" + secStr;
		return "{min}:{sec}".format({'min': minStr, 'sec': secStr});
	},

	render_track: function(data) {
		var track = data['track'];
		var token = data['token'];
		var tpl = "<tr track-id='{id}'>";
		track.weight = track.weight.toFixed(2);
		track['length'] = ardj.format_length(track['length']);
		tpl += "<td class='weight' title='Count: {count}'>{weight}</td>";
		tpl += "<td class='artist'><a href='http://www.last.fm/music/{artist}'>{artist}</a></td>";
		tpl += "<td class='title' title='Track #{id}'>{title}</td>";
		tpl += "<td class='length'>{length}</td>";
		if (token) {
			tpl += "<td class='rocks icon'><a href='/api/track/rocks.json' title='This track rocks'><span>Rocks</span></a></td>"
			tpl += "<td class='sucks icon'><a href='/api/track/sucks.json' title='This track sucks'><span>Sucks</span></a></td>"
			tpl += "<td class='queue icon'><a href='/track/queue.json?track={id}' title='Queue this track'><span>Queue</span></a></td>";
		}
		if (track.download)
			tpl += "<td class='download icon'><a href='{download}' title='Download this track'><span>Download</span></a></td>";
		else
			tpl += "<td class='download icon'></td>";
		tpl += "</tr>";
		return tpl.format(track);
	},

	queue_track: function () {
		$.ajax({
			url: $(this).attr("href"),
			data: {token: ardj.get_token()},
			dataType: "json",
			success: ardj.queue_track_ok,
			error: ardj.ajax_failure
		});
		return false;
	},

	update_track: function(track_id) {
		var token = ardj.get_token();
		$.ajax({
			url: '/api/track/info.json',
			data: {'id': track_id},
			success: function(result) {
				if (result !== 'null') {
					var track = jQuery.parseJSON(result);
					var track_elem = $('tr[track-id="' + track_id + '"]');
					var new_html = ardj.render_track({'track': track, 'token': token});
					track_elem.replaceWith(new_html);
					ardj.update_events(track_elem);
				}
			},
			error: ardj.ajax_failure
		});		
	},

	vote: function () {
		var track_id = $(this).parents("tr:first").attr("track-id");
		$.ajax({
			url: $(this).attr("href"),
			type: "POST",
			data: {track_id: track_id, token: ardj.get_token()},
			dataType: "json",
			success: function (data) {
				ardj.update_track(track_id);
			},
			error: ardj.ajax_failure
		});
		return false;
	},

	queue_track_ok: function () {
		alert("OK, please wait.");
	},

	ajax_failure: function (xhr) {
		alert("Error: " + xhr.responseText);
	},

	get_token: function () {
		return window.localStorage.getItem("ardj_token");
	},

	set_token: function (value) {
		window.localStorage.setItem("ardj_token", value);
	},

    /**
     * Simplifies substring replacement.  Usage:
     * alert("{a}, {b}!".format({a: "hello", b: "world"}));
     */
    format_string: function (args) {
        var formatted = this;
        for (arg in args) {
            var repeat = true;
            while (repeat) {
                var tmp = formatted.replace("{" + arg + "}", args[arg]);
                if (tmp == formatted)
                    repeat = false;
                else
                    formatted = tmp;
            }
        }
        return formatted;
    }
};


$(document).ready(ardj.init);
