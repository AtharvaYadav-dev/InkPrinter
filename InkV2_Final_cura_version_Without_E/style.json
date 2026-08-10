{
    "QMainWindow":[
		{
			"tittle":"SPPL NEW UI",
			"icon":":/logo/SPPL-logo-sq.png",
			"frameless": true,
			"transluscentBg": true,
			"sizeGrip": "sizeGrip",

			"navigation":[
				{
					"minimize":"minimizePushButton",
					"close": "closePushButton",
					"restore":[
						{	
							"buttonName": "restorePushButton",
							"normalIcon": ":./icons/icons/square.svg",
							"maximizedIcon": ":./icons/icons/copy.svg"
						}
					],
					"moveWindow": "headerContainer",
					"tittleBar": "headerContainer"
				}
			]
		}
	],
    "QCustomSlideMenu": [
		{
			"name": "leftMenuContainer",
			"defaultSize": [{
				"width": 45,
				"height": "parent"
			}],
			"collapsedSize": [{
				"width": 45,
				"height": "parent"
			}],
			"expandedSize": [{
				"width": 150,
				"height": "parent"
			}],
			"toggleButton": [{
				"buttonName": "menuPushButton",
				"icons": [{
					"whenMenuIsCollapsed": ":./icons/icons/align-justify.svg",
					"whenMenuIsExpanded": ":./icons/icons/chevron-left.svg"
				}]
			}],
			"menuTransitionAnimation": [{
				"animationDuration": 500,
				"animationEasingCurve": "Linear"
			}]
		},
        {
			"name": "centerMenuContainer",
			"defaultSize": [{
				"width": 0,
				"height": "parent"
			}],
			"collapsedSize": [{
				"width": 0,
				"height": "parent"
			}],
			"expandedSize": [{
				"width": 200,
				"height": "parent"
			}],
			"menuTransitionAnimation": [{
				"animationDuration": 500,
				"animationEasingCurve": "Linear"
			}]
		},
		{
			"name": "notifyContainer",
			"defaultSize": [{
				"width": 0,
				"height": "parent"
			}],
			"collapsedSize": [{
				"width": 0,
				"height": "parent"
			}],
			"expandedSize": [{
				"width": 530,
				"height": 100
			}],
			"menuTransitionAnimation": [{
				"animationDuration": 500,
				"animationEasingCurve": "Linear"
			}],
			"floatPosition": [
				{
					"relativeTo": "centralwidget",
					"position": "bottom-center",
					"shadow":[
						{
							"color": "#000",
							"blurRadius": 20,
							"xOffset": 0,
							"yOffset": 0
						}
					]
				}
			],
			"toggleButton": [{
				"buttonName": "notifyPushButton"
			}]
		}
    ],
	"QCustomQStackedWidget":[
		{
			"name":"mainPages",
			"navigation":[
				{
					"navigationButtons":[
						{
							"homePushButton": "jogPage",
							"programsPushButton": "programPage",
							"printPushButton": "printPage",
							"terminalPushButton": "terminalPage",
							"laserPushButton": "laserconfPage",
							"syringflushPushButton": "syringeflushPage"
						}
					]
				}
			]
	
		},
		{
			"name":"centerMenuPages",
			"navigation":[
				{
					"navigationButtons":[
						{
							"comPushButton": "comPage",
							"settingsPushButton": "settingsPage",
							"infoPushButton": "infoPage",
							"profilePushButton": "profilePage",
							"blackcomPushButton": "blackcomPage"
						}
					]
				}
			]
	
		},
		{
			"name":"infoSubPages",
			"navigation":[
				{
					"navigationButtons":[
						{
							"aboutPushButton": "aboutPage",
							"helpPushButton": "helpPage",
							"back1PushButton": "optionPage",
							"back2PushButton": "optionPage"
						}
					]
				}
			]
	
		}
	],
    "QPushButtonGroup": [
		{
			"Buttons": [
				"homePushButton",
				"programsPushButton",
				"printPushButton",
				"terminalPushButton",
				"laserPushButton",
				"syringflushPushButton"
			],
			"ActiveButton": "homePushButton",
			"Style":[{
				"Active": "background-color: rgb(144, 170, 197);",
				"NotActive": ""
			}]
		},
		{
			"Buttons": [
				"comPushButton",
				"settingsPushButton",
				"infoPushButton",
				"blackcomPushButton"
			],
			"Style":[{
				"Active": "background-color: rgb(167, 198, 229);",
				"NotActive": ""
			}]
		}
	]
}