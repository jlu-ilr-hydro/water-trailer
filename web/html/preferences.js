selectedsource=null;
sourcedited = false;

jeditableOptions = { 
	      tooltip   : "Click to edit...",
	      style		: "inherit"
	    	  
	  };
function posterror(errtext) {
	$('#scheduleerror').html(errtext);
	if (!errtext) {
		getSchedule();
	}	
}
function saveSource(data) {
	$.ajax({
	    type: 'POST',
	    url: '/source/change',
	    data: JSON.stringify(data),
	    contentType: 'application/json',
	    dataType: 'html',
	    error: function() {
				$('#error').html(err + status);
	    },
	    success: posterror
	});
}

function unlinkSource() {
	if (selectedsource) {
		if (confirm('Do you really want to unlink '
				+ selectedsource.name
				+ '? The source goes to archive and is never '
				+ 'reactivated again.'
				)) 
		{
			$.post('/source/unlink',
					{valveid:selectedsource.valveid},
					posterror);
		}
	}
}

function injectSource() {
	if (selectedsource) {
		$.post('/schedule/injectsource',
				{sourceid: selectedsource.id},
				function(errtext) {
					if (errtext) {
						$('#scheduleerror').html(errtext);
					} else {
						window.location.href='/';
					}
					
				});
	}
}

function addSource() {
	// Adds a new source on a specific valve
	
	// get source name
	var soname = prompt('New name for the source');
	if (!soname) { return;}
	var valveid = $('#freevalves').val();
	$.post('/source/add',
			{name:soname,valveid:valveid},
			function(errtext) {
				if (errtext) {
					$('#error').html(errtext);
				} else {
					$('#error').html('I am fine');
					getSchedule();		
				}
    });
	
}



function isEdited() {
	return $('.selected').hasClass('edited');
}
function selectSource() {
	$('#sourceform').hide();
	if (isEdited() && confirm('Save changes? Cancel will discard the changes')) {
		saveSource(selectedsource);
		$('.selected').removeClass('edited');
		return 0;
	} else {
		$('.selected').removeClass('edited');
	}

	$('.sortable li').removeClass('selected');
	if (selectedsource && selectedsource.id == $(this).data('id')) {
		selectedsource = null;
		return 0;
	}

	$(this).addClass('selected');
	for (var i=0;i<allsources.length;++i) {
		if (allsources[i].id == $(this).data('id')) {
			selectedsource = allsources[i];
		}
	}
	$(this).append($('#sourceform'));
	$('#sourceform').show();
	$.each(selectedsource, function(key,value) {
		if (value===null) {
			$('#so'+key).html('N/A');
		} else {
			$('#so'+key).html(value);
		}
	});
	$('#soform textarea').val(selectedsource.comment);
	return 1;
}
function create_source_ul(source,elemtype) {
	return '<'+elemtype+' data-id="'+source.id+'">'
				+ source.name
				+ ' (on V' + source.valveid + ')'
				+ '</'+elemtype+'>'; 
	
}
function updateSchedule(data) {
	// data received from /schedule/sources.json
	selectedsource=null;
	allsources = [];
	//for (var i=0;i<data.schedule.length;++i) allsources.push(data.schedule[i]);
	//for (var i=0;i<data.events.length;++i) allsources.push(data.events[i].source);
	for (var i=0;i<data.sources.length;++i) allsources.push(data.sources[i]);
	
	$('#existingschedules').val(data.name);
	$('#sourceform').hide().appendTo('body');
	$('#schedulename').html(data.name)
	$('#timepersource').html(data.time_per_source);
	
	// Set select field to load schedules
	var html = '<option value="">&lt;empty&gt;</option>';
	
	$.each(data.schedulenames,function(index,item) {
		if (item == data.name) {
			html += '<option value="' + item + '" selected="selected">' + item + '</option>';
		} else {
			html += '<option value="' + item + '">' + item + '</option>';			
		}
	});
	$('#existingschedules').html(html);
	
	html = '';
	
	// Set schedule
	$.each(data.schedule,function(index,item){
		html+=create_source_ul(item,'li'); 
	});
	$('#schedulelist').html(html);
	
	// Set event sources
	html = '';
	$.each(data.events,function(index,item){
		html+='<div class="condition">';
		html+='<span class="editable condition">'+ item.condition + '</span>';
		html+=', blocks for <span class="editable blocktime">' + item.blocktime + '</span> seconds  <a class="button RemoveEventCondition" >-</a><ul data="event_schedule" class="sortable">';
		for(var i=0; i<item.sources.length; i++) {
			html += create_source_ul(item.sources[i],'li');
		}
		html+='</ul></div>';
	});

	$('#eventlist').html(html);
	$('#eventlist .editable').editable(editMe,jeditableOptions);
	// Set unused sources
	html = '';
	$.each(data.sources,function(index,item){
		html+=create_source_ul(item,'li'); 
	});
	$('ul#sourceslist').html(html);
	
	// Add freevalves
	html='';
	$.each(data.freevalves,function(index,item) {
		html+='<option value="' + item + '">V' + item + '</option>';
	});
	$('#freevalves').html(html);
	
	// Define events
	$('.sortable>li').click(selectSource);
	
	
	// Make objects sortable by drag and drop
	$( '.sortable:not(#sourceform)' ).sortable({
			connectWith: ".sortable:not(#sourceform)",
			cancel: ".fix",
			placeholder: ".normal",
			start: function(e, ui) {
			// creates a temporary attribute on the element with the old index
			$("#actual_schedule_save_pos").attr('data-sortable-previndex', ui.item.index());
			},
			  receive: function( event, ui ) {
				// If a item is dragged from the actual schedule to the unused, then we don't want to show it twice
				  if(ui.sender.attr("data") == "actual_schedule" || "event_schedule" == ui.sender.attr("data"))
					{
						ui.item.remove();
					}
					else if(ui.sender.attr("data") == "unused_schedule")
					{
						var posOfoldAndNewLi = parseInt($("#actual_schedule_save_pos").attr('data-sortable-previndex'));
						// li:eq(n) gets the n-th element of a <li> and "before()" inserts the cloned element of what we draged above
						// But it does not work for the last element
						if(parseInt($("#sourceslist li").length) == posOfoldAndNewLi)
						{
							$('#sourceslist').append(ui.item.clone());
						}
						else{
							$('#sourceslist li:eq('+posOfoldAndNewLi+')').before(ui.item.clone());
						}

						$("#actual_schedule_save_pos").removeAttr('data-sortable-previndex'); // clean up this attribute
						}
					}



	}).disableSelection();

}
function getSchedule() {
	// Loads the actual schedule as a json object
	// and runs updateSchedule with the received data
	$.ajax({ 
			url: '/schedule/sources.json', 
			dataType: 'json', 
			data: null, 
			success: updateSchedule, 
			timeout: 10000, // 10 second timeout,
			error: function(jqXHR, status, errorThrown){   
				$('#scheduleerror').html(errorThrown + '\n' + status);
			}
	}); 
}
function addEventCondition(condition) {
	if (!condition) {
		condition = prompt('Enter a valid Python condition:');
	}
	if (condition) {
		var html='<div class="condition">';
		html+='<span class="editable condition">'+ condition + '</span>';
		html+=', blocks for <span class="editable blocktime">0.0</span> seconds <a class="button RemoveEventCondition" >-</a>';
		html += '<ul data="event_schedule" class="sortable ui-sortable">';
		html += '</ul></div>';

		$(html).appendTo('#eventlist');
		$('#eventlist .editable').editable(editMe,jeditableOptions);
		
		$('.sortable:not(#sourceform)').sortable({
				connectWith: ".sortable:not(#sourceform)",
				cancel: ".fix",
				placeholder: ".normal",
		}).disableSelection();
	}

}

function loadSchedule() {
	$.ajax({
	    type: 'POST',
	    url: '/schedule/load',
	    data: JSON.stringify({name:$('#existingschedules').val()}),
	    contentType: 'application/json',
		timeout: 10000, // 10s timeout
	    dataType: 'html',
	    error: function(jqXHR, status, errorThrown) {
				$('#error').html(errorThrown + status);
	    },
	    success: posterror
	});
}

function clearSchedule() {
	$.post('/schedule/clear',null,posterror);
}
function saveSchedule() {
	return saveScheduleAs($('#existingschedules').val());
}
function saveScheduleAs(schedulename) {
	var sourceids = {
		schedule:[],
		events:[],
		unused:[]
	};
	if (!schedulename) {
		schedulename = prompt('New schedule name:');
	}
	if (!schedulename) {
		alert('No name given...');
		return;
	}
	
	$('#schedulelist>li').each(function(index) {
		sourceids.schedule.push($(this).data('id'));
	});

	$('#eventlist div.condition').each(function(index) {
		var taglist = [];
		$(this).find('li').each(function(k,v) {
			taglist.push($(v).data('id'));
		});

		sourceids.events.push({
			condition: $(this).find('span.condition').text(),
			blocktime: $(this).find('span.blocktime').text(),
			tag: taglist
		});
	});

	$('#sourceslist>li').each(function(index) {
		sourceids.unused.push($(this).data('id'));
	});
	sourceids.schedulename = schedulename;
	sourceids.time_per_source = parseFloat($('#timepersource').html()) * 60.0; 
	$.ajax({
	    type: 'POST',
	    url: '/schedule/write',
	    data: JSON.stringify(sourceids),
	    contentType: 'application/json',
	    dataType: 'html',
	    error: function(jqXHR, status, errorThrown) {
			$('#error').html(errorThrown + status);
	    },
	    success: posterror
	});
}

function killSchedule() {
	if (confirm('Do you really want to delete schedule ' +  $('#existingschedules').val())) {
		$.ajax({
		    type: 'POST',
		    url: '/schedule/kill',
		    data: JSON.stringify({name:	$('#existingschedules').val()}),
		    contentType: 'application/json',
		    dataType: 'html',
		    error: function(jqXHR, status, errorThrown) {
					$('#error').html(errorThrown + status);
		    },
		    success: posterror
		});		
	}
}

function editMe(newtext,settings) {
	var key = $(this).prev().html();
	var val = $(this).text();
	if ($(this).attr('id') && newtext) {
		if (!newtext || newtext == 'N/A')
			selectedsource[$(this).attr('id').substring(2)] = null;
		else
			selectedsource[$(this).attr('id').substring(2)] = newtext;		
	} 
	if (newtext) {
		$(this).html(newtext);
		$('.selected').addClass('edited');			
	}
	return newtext;

}
function editHtml(newtext,settings) {
	return newtext;
}
$(function() {
	getSchedule();
	$('#sourceform').click(function(e) {
		e.stopPropagation();
	});
	$('#scheduleprops .editable').editable(editHtml,jeditableOptions);
	$('#sourceform .editable').editable(editMe,jeditableOptions);
	$('#sourceform .comment').click(function(e){
		$('#sourceform .editarea').show().find('textarea').val($(this).html()).focus();
		$(this).hide();
		e.stopPropagation();
	});
	$('#existingschedules').change(loadSchedule);
	$('#someasure').click(injectSource);
	$('#sosave').click(function() {
		if (selectedsource) {
			saveSource(selectedsource);
			$('#sourceform').removeClass('edited');
		}

	});
	$('#sourceform .editarea .button').click(function(e) {
		var commentdiv = $('#socomment');
		if ($(this).data('key') == 'save') {
			var text = $(this).prev('textarea').val();
			commentdiv.html(text);
			selectedsource.comment = text;
			$('.selected').addClass('edited');
			
		} 
		$(this).parent('.editarea').hide();
		commentdiv.show();
		e.stopPropagation();
	});


	// That's how you can add event listeners to dynamic content and you do not have to define everything new after inserting an element
	// #eventlist is static, otherwise it will not work
	$('#eventlist').on('click', '.RemoveEventCondition', function() {
		$(this).parent().remove();
	});



});
