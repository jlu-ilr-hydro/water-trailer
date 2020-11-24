/**
 * 
 */

// Globals

// Global settings of the page
var Settings = null;
var statustimeout = null;
var lastmousemove = Date.now();
// After 10 min of no mouse move go to sleep mode: refresh only once per minute
var sleeptime = 10 * 60 * 1000;
var tstart_ajax = Date.now();


function fmtTime(t,timeonly) {
	if (timeonly && false) {
		return moment(t).format('HH:mm:ss');
	} else {
		return moment(t).format('YYYY-MM-DD HH:mm:ss');
	}

}

if (!String.prototype.format) {
  String.prototype.format = function() {
    var args = arguments;
    return this.replace(/{(\d+)}/g, function(match, number) { 
      return typeof args[number] != 'undefined'
        ? args[number]
        : match
      ;
    });
  };
}


function pretty(val) {
	// Formats floats and times more pretty
	if (isFloat(val)) {
		return val.toPrecision(5);
	} else if (isInteger(val)) {
		return val;
	} else if (moment(val, moment.ISO_8601).isValid()) {
		return fmtTime(val);
	} else {
		return val;
	}
}

function jsonvalue2html(elem, name, obj, creatediv) {
	var newchild;
	if (obj == null || obj == {}) {
		newchild = $('<div id="data_dev_view_'+name+'" class="child warning">'+name+'</div>').appendTo(elem);
	} else if (typeof obj == "object") {

		if (creatediv) {
			newchild = $('<div id="data_dev_view_'+name+'" class="child togglechildren"><span class="devcap_triangle devcap_triangle_closed"> &#9658;</span>'+name+'</div>').appendTo(elem);
		} else {
			newchild = elem;
		}
		$.each(obj,function(key,value){
			jsonvalue2html(newchild,name + '.' + key, value, true);
		});


	} else {
			var keyspan = '<span class="key" data-var="name">name</span>'.replace(/name/g,name);
			var vspan;
			vspan =  '<span class="value">' + pretty(obj) + '</span>';
			newchild = $('<div id="data_dev_view_'+name+'" class="child"></div>').appendTo(elem);
			newchild.append(keyspan);
			newchild.append(vspan);
	}

}
function ondevicekeyclick(e) {
	//Triggered by click
	Settings.frontvalues.push($(this).data('var'));
	e.stopPropagation();
	reloadstatus();
}
function setPlotValue(e) {
	e.stopPropagation();
	Settings.plot.variable = $(this).data('var');
	Settings.plot.caption = $(this).data('var');
	// Clear the plot data
	Settings.plot.data = [];
	
	// Save the settings
	window.sessionStorage.Settings = JSON.stringify(Settings);

	
	$('h1.plotcaption').html(Settings.plot.caption + ' [' + Settings.plot.data.length + ']');
	reloadstatus();
	
}
// Creates all the device data divs in the center pane
function updatedevices(data) {


	// Show the selected device values
	var html = '<table class="small">';
	var fv = Settings.frontvalues;
	$.each(fv,function(index) {
		var item = fv[index];
		if (item) {
			var devnames = item.split('.');
			var value = data.devices;
			var i;
			for(i=0; i<devnames.length; ++i) {
				if (value) {
					value = value[devnames[i]];
				}
			}
		}
		html += '<tr><td>';
		html += '<a class="button" onclick="Settings.frontvalues.splice('+index+',1);reloadstatus()" title="remove this value from the watch list">&times;</a>';
		html += '<a class="button plotvalue" data-var="' + item + '" title="plot this device value">P</a>';
		html += '</td><td>' + item + '</td>';
		html += '<td>' + pretty(value) + '</td>';
		html += '</tr>'
	});
	html += '</table>';
	var frontvalues = $('#frontvalues').html(html);
	// I removed this function here to make it a static event listener


	// Update the device values
	// create a dummy element to append the new device data to
	var elem = $('<div style="display:none"></div>');
	// for each device, make an element for the data description
	// and combine it with the active state of the device
	$.each(data.devices,function(key,value) {
		// Add a caption for the device as h3
		// and the active / deactive flagg &#9724;
		var actDea_togg_button = '<a class="device_activate active button" data-key="'+key+'">&#9724;</a>';
		if(typeof value.active != "undefined")
		{

			if(!value.active)
			{
				actDea_togg_button = '<a class="device_activate stop button" data-key="'+key+'">&#9658;</a>';
			}
		}
		var devcap = $('<h3 class="devcap"><span class="devcap_triangle devcap_triangle_closed"> &#9658;</span>'+key+' </h3>' +
			actDea_togg_button).appendTo(elem);

		if (value.ready) {
			devcap.addClass('active');
		}
		// Add the element holding the device values
		var develem = $('<div id="data_dev_view_'+key+'" class="normal"></div>').appendTo(elem);

        // and make the currently visible object id's visible later
			develem.css("display","none");

		// add the device values to the element
		jsonvalue2html(develem,key,value);
	});


	// find all currently visible id's of hidden classes
	var visible_ids = {"normal":[],"toggle":[]};
	$.each($('#devices').find(".child"),function(key,value){
		if($(value).not("h3").not(".device_activate").length == 1)
		{
			if($(value).hasClass("togglechildren"))
			{
				//console.log($(value).children());
				if($($(value).children()[1]).css("display") == "block")
				{
					visible_ids.toggle=visible_ids.toggle.concat($(value).attr("id"));
				}
			}
		}

	});

	$.each($('#devices').children(),function(key,value){
		if($(value).not("h3").not(".device_activate").length == 1)
		{
			if($(value).css("display") == "block")
			{
				visible_ids.normal=visible_ids.normal.concat($(value).attr("id"));
			}
		}
	});

	// Exchange old element with the new elem
	var dev = $('#devices');
	dev.html(elem.html());
	dev.find('.key[data-var="' + Settings.plot.variable + '"]').addClass('active');
	dev.find('.key').click(ondevicekeyclick);
	dev.find('.devcap').click(function() {
		$(this).next().next().slideToggle(100);
	});
	var closeables = dev.find('.togglechildren');
	closeables.children().not(".devcap_triangle_closed").not(".devcap_triangle_togglechild_opened").hide();
	closeables.click(function(e) {
		e.stopPropagation();

		$(this).children().not(".devcap_triangle_closed").not(".devcap_triangle_togglechild_opened").slideToggle(200);

		if($($(this).children()[0]).hasClass("devcap_triangle_closed")){
			$($(this).children()[0]).removeClass("devcap_triangle_closed");
			$($(this).children()[0]).addClass("devcap_triangle_togglechild_opened");
		}
		else if($($(this).children()[0]).hasClass("devcap_triangle_togglechild_opened"))
		{
			$($(this).children()[0]).removeClass("devcap_triangle_togglechild_opened");
			$($(this).children()[0]).addClass("devcap_triangle_closed");
		}



	});
	// After replacing we have to reopen the settings
	$.each(visible_ids.normal, function(index, item) {
		var selector='';
		selector += '#' + item + ' ';
		$(selector).css("display","block");
		$($(selector).prev().prev().children()[0]).removeClass("devcap_triangle_closed");
		$($(selector).prev().prev().children()[0]).addClass("devcap_triangle_opened");
    });
	$.each(visible_ids.toggle, function(index, item) {

		$(document.getElementById(item)).children().css("display","block");
		$($(document.getElementById(item)).children()[0]).removeClass("devcap_triangle_closed");
		$($(document.getElementById(item)).children()[0]).addClass("devcap_triangle_togglechild_opened");
    });
	// After reloading the view the toggle triangles are broken, so fix them back
	$(".devcap_triangle").css("display","inline-block");



	// delete the dummy element
	elem.remove();
	
}


function updatestatus(alldata) {
	var data = alldata[0];
	var scheduledata = alldata[1];
	var html="";
	$('#clock').html(data.current.time);
	if (data.current.active) {
		$('h1.schedule').removeClass('warning').addClass('active');
	} else {
		$('h1.schedule').removeClass('active').addClass('warning');
	}
	if (data.current.sample) {
		$('#presentheader').html('present: ' + data.current.sample.name);		
	}
	// Set the progress
	html = "";
	$.each(data.current.progress,function(index,item){
		var key = item[0];
		var value = item[1];
		html += '<div class="list progress" id="progress' + key + '"><span class="progress-label">' + key + 
				'</span><div class="progress-bar" '+
				'style="width:' + (value * 100).toFixed(2) + '%;">'+
				'</div></div>'
	});
	$('#present').html(html);
	
	updatedevices(data);
	
	// delete an error text, if present
	$('#error').html('');
	if (data.logbook) {
		updatelogs(data.logbook);
	}
	
	// Add data to the plot 
	if (Settings.plot.variable) {
		var devnames = Settings.plot.variable.split('.');
		var value = data.devices;
		var i;
		for(i=0; i<devnames.length; ++i) {
			if (value)
				value = value[devnames[i]];
		}

		if (value) {
			if (Settings.plot.data.length == Settings.plot.length) {
				Settings.plot.data.shift(1);
			} else if (Settings.plot.data.length > Settings.plot.length){
				Settings.plot.data = Settings.plot.data.slice(Settings.plot.data.length - Settings.plot.length + 1);
			}
			Settings.plot.data.push([Date.now(),value]);
		}
		
	}

	// Update the measurement step
	makeplot();
	$('h1.status').removeClass('reading');
	updateschedule(scheduledata);
	$('#scheduleinfo').html('reload: ' + (Date.now()-tstart_ajax) + ' ms');
	//$('#scheduleinfo').html('no mousemove since: ' + ((Date.now()-lastmousemove)*1e-3).toFixed(1) + ' s');

}

function reloadstatus() {
	
	clearTimeout(statustimeout);
	
	if (Date.now()-tstart_ajax<100) {
		return;
	}
	
	var minTime = 0.0;
	var status_refreshtime = $('#statusrefreshtime').val();
	if (Date.now() - lastmousemove > sleeptime && status_refreshtime) {
		minTime = 60 * 1000;
	}
	Settings.refreshtime = Math.max(status_refreshtime, minTime);
	Settings.plot.length = parseInt($('#statusmaxplotlength').val());
	Settings.log.count = $('#logcount').val();
	Settings.log.level = $('#loglevel').val();
	
	window.sessionStorage.Settings = JSON.stringify(Settings);
	tstart_ajax = Date.now();
	$('h1.status').addClass('reading');
	$.ajax({ 
				url: 'status', 
				dataType: 'json', 
				data: {logcount:Settings.log.count,
					   loglevel:Settings.log.level,
					   nhist: Settings.npast,
					   nfuture: Settings.nfuture
				}, 
				success: updatestatus, 
				timeout: 10000, //10 second timeout,
				error: function(jqXHR, status, errorThrown){   
					$('#error').html(errorThrown);
				} 
	}); 
	
	if (Settings.refreshtime) {
		statustimeout = setTimeout(reloadstatus,Settings.refreshtime);
	}
}
function updateschedule(data) {
	// Schedule name
	$('h1.schedule').html(data.name);


	// History --> save open Elements before overwrite all
	var ids_to_open_in_future = [];
	$.each($('#past').children(),function(k,v){
		var obj = $($(v).children()[0]);

		if(obj.css("display") == "block")
		{
			ids_to_open_in_future = ids_to_open_in_future.concat(obj.attr("id"));
		}
	});

	// History --> Delete past Elements but make the description visible which is stored in *ids_to_open_in_future*
	var past = $('#past').html('');
	$.each(data.history,function(index,item){
		var html = '<div class="normal list">' + item.source.name + ' : ' + fmtTime(item.time) + '</div>';
		var id = 'list_details_'+index;
		var display = "none";


		if($.inArray(id, ids_to_open_in_future) > -1)
		{
			display = "block";
		}
		var dethtml = '<div id="'+id+'" style="display: '+display+';" class="detail normal">';
		$.each(item.values,function(key,value){
			dethtml+='<div class="small">'+
							'<span class="key">'+key+'</span>'+
							'<span class="value">' + pretty(value) + '</span>'+
						'</div>';
		});
		dethtml += '</div><!--detail-->';
		
		var elem = $(html).appendTo($('#past'));
		$(dethtml).appendTo(elem);
		if (!item.ok) {
			elem.addClass('warning');
		}
	});
	past.find('.list').click(function() {

		var visible = $($(this).children()[0]).css("display");
		$('.detail').hide();
		if(visible == "none")
			$($(this).children()[0]).show();
		else if(visible == "block")
			$($(this).children()[0]).hide();
	});

	// Show name of current source
	if (data.current) {
		$('#presentheader').html('present:' + data.current.name);
		
	} else {
		$('#presentheader').html('waiting...');
	}
	
	// Future
	$('#future').html('');
	$.each(data.future,function(index,item){
		$('<div class="list normal"></div>')
		.html(fmtTime(item.due,true) + ': ' + item.name)
		.appendTo($('#future'));
	});
	$('#schedule_pos').html('actual pos: ' + data.pointer);

}


function updatelogs(data) {
	
	$('#logs').html('');
	$.each(data,function(index,item) {
		$('#logs').append('<li class="log level'+item.level+'"'+
						     ' data-id="'+item.id+'">' + 
							fmtTime(item.time,true) +
							': ' + item.msg +
  						'</li>'); 
	});		
}


function makeplot() {
	var data = Settings.plot.data;
	var label = Settings.plot.caption;
	$('h1.plotcaption').html('plot: ' + label + ' [' + data.length + ']');
	
	var axoptions = {
		color : '#BBB',
		tickColor : '#BBB',
		font : {
			color : 'white',
			size : 16
		}
	};
	var xaxoptions = $.extend({mode:'time',timezone:'browser'},axoptions);
	var options = {
		canvas : false,
		series : {
			lines : {
				show : true
			},
			points : {
				show : true,
				fill : true
			}
		},
		xaxis : xaxoptions,
		yaxis : axoptions,
		grid : {
			color : '#BBB',
			backgroundColor : null,
			borderWidth : 2,
			borderColor : '#BBB'
		}
	};

	$.plot("#actualplot", [{
			label : label,
			data : data,
			color : '#88AAFF'
		}], 
		options);				
}

function isFloat(n) {
	return n === +n && n !== (n|0);
}

function isInteger(n) {
	return n === +n && n === (n|0);
}

function schedulestart(value){
	$.post('setactive',{value:value},function(error){
		$('#error').html(error);
		if (error) {
			reloadstatus();
		} else {
			window.location.reload()
		}

	});
}

$(function() {
	Settings = JSON.parse(window.sessionStorage.getItem('Settings'));
	Settings = Settings || {};
	Settings.plot = Settings.plot ||  {
			variable : "",
			caption : "",
			length : 10,
			data : []
	};
	Settings.log = Settings.log || {count:10,level:5};
	Settings.frontvalues = Settings.frontvalues || []
	Settings.npast = Settings.npast || 5
	Settings.nfuture = Settings.nfuture || 5	
	$('#statusrefreshtime').val(Settings.refreshtime);
	$('#statusmaxplotlength').val(Settings.plot.length);
	$('#logcount').val(Settings.log.count);
	$('#loglevel').val(Settings.log.level);

	// If there is no value to plot disable plot view
	if(Settings.plot.variable == "")
	{
		$(".plotcontainer").css("display","none");
	}

	setTimeout(reloadstatus,100);
	$('body').mousemove(function() {
		if (Date.now() - lastmousemove > Math.max(sleeptime, $('#statusrefreshtime').val())) {
			reloadstatus();
		}
		lastmousemove = Date.now();

	});
	$('.child .open').click(function(){
		$(this).parent().children('.child').toggle('fast');
	});
	$('.leftpane a.button').click(reloadstatus);
	$('select.statusprop').change(reloadstatus);
	$('#plot').click(makeplot);
	$('#shutdown_server').click(function() {
		if (confirm('Are you sure to shut down the server?')) {
			$.post('shutdown_server', {}, function(response) {
				$('.plotcaption').html(response).addClass('error');
			});
		}
	});

	// That's how you can add event listeners to dynamic content and you do not have to define everything new after inserting an element
	// #eventlist is static, otherwise it will not work
	$('#frontvalues').on('click', '.plotvalue', setPlotValue);
	$('#frontvalues').on('click', '.plotvalue', function(){
		$(".plotcontainer").css("display","block");
	});
	$('#devices').on('click', '.device_activate', function(){
		console.log($(this).attr("data-key"));
		$.ajax({
				url: 'tools/devices_toggle_active/',
				dataType: 'json',
				type: 'POST',
				data: {
					devicename:$(this).attr("data-key")
				},
				success: function(result){
					$('#error').html(result);
					reloadstatus();
				},
				error: function(jqXHR, status, errorThrown){
					$('#error').html(jqXHR.responseText);
					reloadstatus();
				}

		});
	});

	$('#devices').on('click', '.devcap', function(){
		if($(this).children().hasClass("devcap_triangle_closed")){
			$(this).children().removeClass("devcap_triangle_closed");
			$(this).children().addClass("devcap_triangle_opened");
		}
		else if($(this).children().hasClass("devcap_triangle_opened"))
		{
			$(this).children().removeClass("devcap_triangle_opened");
			$(this).children().addClass("devcap_triangle_closed");
		}

	});
	$('#schedule_skip_next').click(function(){
		$.post('schedule/skip_next', {}, function() {
			reloadstatus();
		});
	});

	$(".plotcaption").click(function(){
		$(".plotcontainer").css("display","block");
	});


});

