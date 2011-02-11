/**
 * скрипт простенького ajax-чатика
 * @author hakimovis
 * Сообщения в чат ожидаются от сервера в следующем виде (json):
 * 	{
 *		"9":{"datetime":"01.01.11 1:11","nick":"userNick","message":"message text!"},
 *		"8":{"datetime":"11.02.11 23:54","nick":"userNick","message":"message text"}
 *	}
 *
 * Сообщения от пользователя отправляются на сервер в виде POST
 * запросов: userNick: имяПользователя,	sendText: текстСообщения
 * 
 * Шаблон чата это обычный html, можно разукрашивать как душе угодно.
 */

//глобальные переменные 
srvUrl="/"; //ссылка на сервер, пишется перед chatTemplateFile и прочими
chatTemplateFile='chattemplate.txt';	//файл шаблона чатика, html
getChatLogUrl='getlogs.php'; //адрес откуда спрашиваются сообщения чата
sendPostsUrl='http://stream.tmradio.net:8000/'; //адрес куда отправляются POST запросы
//alert('start!');

//подгружаем файл шаблона и выставляем на странцу
$.ajax({  
    url: srvUrl+chatTemplateFile, global: false, type: "GET",
    beforeSend: function(){$("#loading").fadeIn();},
    complete: function(){$("#loading").fadeOut();},
    dataType: "html",
    success: function(data) {
    	$('#chatApplication').html(data);
    	setEvents();
    	autoUpdateOn();
    	getChatMessages();
	}
});
/**
 * выставляем события
 */
function setEvents(){
	$('#acceptNick').click(function(){
		nick=$('#nickField').val();
		$('#storedUserNick').attr("value",nick);
		$('#loginForm').html('');
		$('#sendMessageForm').css("display","block");
		$('#chatForm').css("display","block");
	});
	$('#sendText').click(function(){
		msg=$('#postTextInput').val();
		sendMessage(msg);
	});
};
/**
 * включение автообновления
 */
function autoUpdateOn(){
	autoUpdateState=true;
	autoUpdateChat=window.setInterval(getChatMessages,5000);
	return autoUpdateChat;
};
/**
 * выключение автообновления
 */
function autoUpdateOff(){
	autoUpdateState=false;
	clearInterval(autoUpdateChat);
}
/**
 * проверка состояния чекбокса и включение или выключение автообновления
 */
function chechAutoUpdate(){
	if ($('#autoUpdateCheckBox').attr('checked') && !autoUpdateState) autoUpdateOn();
	if (!$('#autoUpdateCheckBox').attr('checked') && autoUpdateState) autoUpdateOff();
};
/**
 * получение списка сообщений с сервера и добавление в контейнер чата
 */
function getChatMessages(){
	lastNum=$('#lastMessageNum').val();
	$.ajax({  
	    url: srvUrl+getChatLogUrl, global: false, type: "GET",
	    beforeSend: function(){$("#loading").fadeIn();},
	    complete: function(){$("#loading").fadeOut();},
	    data: ({
	    		nickname:$('#storedUserNick').val(),
	    		}),
	    dataType: "json",
	    success: function(data) {
	    	var msgs='';
	    	for(var num in data) {
	    		row=data[num];
	    		msgs+=row['datetime']+' <b>'+row['nickname']+':</b> '+row['message']+'<br>';
	    	};
	    	$('#chatMessages').append(msgs);
	    	$('#lastMessageNum').attr("value",num);
	    	$('#autoUpdateCheckBox').click(function(){chechAutoUpdate();});
		},
		error: function (a, b, c) {
			// ... handle me ...
		}
	});	
};
/**
 * отправка сообщения
 * @param msg текст сообщения
 */
function sendMessage(msg){
	nick=$('#storedUserNick').val();
	text=$('#postTextInput').val();
	$.ajax({  
	    url: sendPostsUrl, global: false, type: "POST",
	    beforeSend: function(){$("#loading").fadeIn();},
	    complete: function(){$("#loading").fadeOut();},
	    data: ({
	    		nickname:nick,
	    		message:text
	    		}),
	    dataType: "html",
	    success: function(data) { 	
			$('#postTextInput').attr("value","");
			$('#logs').append('<br>'+data);
		}, error: function (a, b, c) {
			// ... handle me ...
		}
	});	
};
