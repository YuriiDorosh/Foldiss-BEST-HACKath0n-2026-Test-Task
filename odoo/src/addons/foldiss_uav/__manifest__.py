{
    "name": "Foldiss UAV Flight Analysis",
    "summary": "Parse ArduPilot .BIN flight logs, compute metrics, 3D trajectory, AI analysis",
    "version": "18.0.1.0.0",
    "category": "Operations",
    "author": "Foldiss",
    "license": "LGPL-3",
    "depends": ["base", "mail"],
    "data": [
        "security/ir.model.access.csv",
        "views/uav_mission_views.xml",
        "views/menus.xml",
    ],
    "application": True,
    "installable": True,
    "auto_install": False,
}
