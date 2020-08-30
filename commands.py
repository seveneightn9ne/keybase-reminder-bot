def advertise_commands(bot):
    remind_me_extended = """Set a reminder at a specific time. Examples:
    ```
    !remind me [when] to [what]
    !remind me to [what] [when]```"""
    delete_extended = """Examples:
    ```
    !delete the reminder to [what]
    !delete the [when] reminder
    !delete reminder #2```"""
    tz_extended = """Set your timezone to [tz]. This changes when any upcoming reminders will happen. Examples:
    ```
    !timezone GMT
    !timezone US/Pacific```"""
    bot.chat.execute({
        "method": "advertisecommands",
        "params": {
            "options": {
                "alias": "Reminder Bot",
                "advertisements": [{
                    "type": "public",
                    "commands": [
                            {
                            "name": "help",
                            "description": "See help with available commands.",
                            },
                            {
                            "name": "remind me",
                            "description": "Set a reminder.",
                            "extended_description": {
                                    "title": "*!remind me*",
                                    "desktop_body": remind_me_extended,
                                    "mobile_body": remind_me_extended,
                                }
                            },
                            {
                            "name": "list",
                            "description": "Show upcoming reminders.",
                            },
                            {
                            "name": "delete",
                            "description": "Delete a reminder.",
                            "extended_description": {
                                    "title": "*!delete*",
                                    "desktop_body": delete_extended,
                                    "mobile_body": delete_extended,
                                }
                            },
                            {
                            "name": "timezone",
                            "description": "Set your timezone.",
                            "extended_description": {
                                    "title": "*!timezone*",
                                    "desktop_body": tz_extended,
                                    "mobile_body": tz_extended,
                                }
                            },
                            {
                            "name": "source",
                            "description": "Learn about my beginnings.",
                            },
                        ],
                    }
                ],
            },
        },
    })

def clear_command_advertisements(bot):
    bot.chat.execute({
        "method": "clearcommands",
        "params": {},
    })
