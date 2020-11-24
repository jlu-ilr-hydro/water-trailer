/* development tests
var t = ["a.b.c", "a.b.s", "name.tes.a.b", "o"];

console.log(buildJsonObject(t));
*/

/*
This function generates out of a objects of keys with their values a suitable JSON object
*/
function buildJsonObject(t) {


    var oo = [];

    $.each(t,function(key,vall){

        var list = key.split(".");
        var c = list.length - 1;
        var tmpObj = {};

        for (var j = c; j >= 0; j--) {
            //console.log(j+" "+c);
            if (c == j) {
                tmpObj[list[j]] = vall;

            } else {
                var tmps = {};
                tmps[list[j]] = tmpObj;
                tmpObj = tmps;
            }

        }
        oo.push(tmpObj);
    });
//console.log(oo);

    function constructHasName(ccc, name) {
        var nameExists = false;
        for (i in ccc) {
            if (ccc[i].name === name) {
                nameExists = true;
                break;
            }
        }
        return nameExists;
    }

    return createSubObj(oo);

    function createSubObj(obj) {
        var back = [];
        for (var l in obj) {

            if(obj[l][Object.keys(obj[l])[0]]!= null)
            {

            if (typeof obj[l][Object.keys(obj[l])[0]].hasOwnProperty("comment")) {
                var existChild = true;
            }
            else {
                var existChild = false;
            }
            }
            else{
                var existChild = false;
            }

            if (!constructHasName(back, Object.keys(obj[l])[0])) {
                var tmpadob = {"name": Object.keys(obj[l])[0]};
                if (existChild) {
                    // get all objects which have this key but without the first key
                    var tosend = [];
                    for (var i in obj) {
                        if (Object.keys(obj[i])[0] === Object.keys(obj[l])[0]) {
                            tosend.push(obj[i][Object.keys(obj[l])[0]]);
                        }
                    }

                    if(tosend[0] != null)
                    {
                        if(!tosend[0].hasOwnProperty("comment"))
                        {
                        tmpadob["child"] = createSubObj(tosend);
                        }
                        else{
                            tmpadob["v"] = obj[l];
                        }

                    }
                    else{
                        tmpadob["v"] = obj[l];
                    }

                }
                else {
                    tmpadob["v"] = obj[l];
                }
            back.push(tmpadob);
            }

        }
        return back;
    }
}