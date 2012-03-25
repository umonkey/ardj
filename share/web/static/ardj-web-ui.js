ardj = {
	init: function () {
		String.prototype.format = ardj.format_string;

		if (ardj.get_token())
			$("body").addClass("authenticated");
		else
			$("body").addClass("anonymous");

		$("#searchform input:first").focus();

		$("#searchform form").submit(function () {
			$.ajax({
				url: $(this).attr("action"),
				dataType: "json",
				data: $(this).serialize(),
				success: ardj.search_complete
			});
			return false;
		});

		$("#searchform .eg").click(ardj.sample_search);

		$(".login").click(ardj.show_login_form);

		$("#loginform form").submit(ardj.submit_login_form);

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

	/**
	 * Форматирование результатов запроса.
	 *
	 * Отформатированный результат отправляется в #searchresult.
	 *
	 * @param object data Описание результата.  Массив tracks должен содержать
	 * информацию о дорожках.
	 */
	search_complete: function (data) {
		var html = "", tpl;

		var token = ardj.get_token();

		if (data.scope == "search")
			html += "<h2>Search results:</h2>";
		else if (data.scope == "recent")
			html += "<h2>Recently played tracks</h2>";

		if (data.tracks.length) {
			html += "<table><tbody>";

			data.tracks.forEach(function (track) {
				track.weight = track.weight.toFixed(2);
				tpl = "<tr track-id='{id}'>";
				tpl += "<td class='weight'>{weight}</td>";
				tpl += "<td class='artist'><a href='http://www.last.fm/music/{artist}'>{artist}</a></td>";
				tpl += "<td class='title'>{title}</td>";
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

				html += tpl.format(track);
			});

			html += "</tbody></table>";
		} else {
			html += "<p>Nothing.</p>";
		}

		html = $("#searchresult").html(html);
		html.find("a").attr("target", "_blank");
		html.find(".queue a").click(ardj.queue_track);
		html.find(".rocks a, .sucks a").click(ardj.vote);

		$("#searchform input:first").focus();
	},

	queue_track: function () {
		$.ajax({
			url: $(this).attr("href"),
			dataType: "json",
			success: ardj.queue_track_ok,
			error: ardj.ajax_failure
		});
		return false;
	},

	vote: function () {
		var track_id = $(this).parents("tr:first").attr("track-id");
		$.ajax({
			url: $(this).attr("href"),
			type: "POST",
			data: {track_id: track_id, token: ardj.get_token()},
			dataType: "json",
			success: function (data) {
				alert("OK");
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
