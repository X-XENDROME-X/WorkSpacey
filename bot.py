import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timedelta
import os
import pytz
import re

from dotenv import load_dotenv
load_dotenv()

intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.voice_states = True
intents.members = True 
intents.message_content = True 

bot = commands.Bot(command_prefix='/', intents=intents)

user_status = {}
users_to_remind = {}
users_on_break = {}

est = pytz.timezone('US/Eastern')

@tasks.loop(minutes=1)
async def remind_to_take_break():
    now = datetime.now(est)
    for user_id, status in user_status.items():
        if status["status"] == "online" and user_id not in users_on_break:
            active_time = now - status["last_active"]
            if active_time >= timedelta(hours=5) and (status["last_notified"] is None or now - status["last_notified"] >= timedelta(hours=5)):
                user = await bot.fetch_user(user_id)
                try:
                    await user.send("Reminder: You've been working for 5 hours. Please take a break!")
                    user_status[user_id]["last_notified"] = now
                except discord.Forbidden:
                    pass
                
                
@tasks.loop(minutes=1)
async def remind_long_break():
    now = datetime.now(est)
    for user_id, user in users_on_break.items():
        break_start_time = user_status[user_id]["timestamp"]
        break_duration = now - break_start_time
        if break_duration >= timedelta(hours=5) and (user_status[user_id]["last_notified"] is None or now - user_status[user_id]["last_notified"] >= timedelta(hours=5)):
            try:
                await user.send("Reminder: You've been on break for 5 hours. Please consider logging off.")
                user_status[user_id]["last_notified"] = now
            except discord.Forbidden:
                pass           

@bot.event
async def on_ready():
    print(f'Bot is ready. Logged in as {bot.user}')
    await bot.change_presence(status=discord.Status.online)
    await bot.tree.sync()
    if not remind_to_take_break.is_running():
        remind_to_take_break.start()
    if not remind_long_break.is_running():
        remind_long_break.start()
        
        
@bot.tree.command(name="logon", description="Log on and set your current work status.")
async def logon(interaction: discord.Interaction, work: str):
    now = datetime.now(est)
    user_status[interaction.user.id] = {
        "status": "online",
        "work": work,
        "timestamp": now,
        "last_notified": None,
        "last_active": now
    }
    timestamp = datetime.now(est).strftime("%Y-%m-%d %H:%M:%S")
    message = f'{interaction.user.mention} Logged On: {timestamp}. \nWork to be Done: {work}'
    
    await interaction.response.send_message(message)
    
    if interaction.user.id not in users_to_remind:
        users_to_remind[interaction.user.id] = interaction.user
    
    if not remind_to_join_vc.is_running():
        remind_to_join_vc.start()

@tasks.loop(minutes=3)
async def remind_to_join_vc():
    for user_id in list(users_to_remind.keys()):
        user = users_to_remind[user_id]
        
        if user_id in users_on_break:
            continue 

        if user.voice and user.voice.channel:
            pass
        else:
            try:
                await user.send("Reminder: Please join a voice chat channel.")
            except discord.Forbidden:
                pass
            
    if not users_to_remind:
        remind_to_join_vc.stop()

@bot.event
async def on_voice_state_update(member, before, after):
    if member.id in users_to_remind and not after.channel:
        try:
            await member.send("Reminder: Please join a voice chat channel.")
        except discord.Forbidden:
            pass

@bot.tree.command(name="logoff", description="Log off and set your work status to offline.")
async def logoff(interaction: discord.Interaction, work: str, attachment: discord.Attachment = None):
    user_status[interaction.user.id] = {
        "status": "offline",
        "work": work,
        "timestamp": datetime.now(est),
        "last_notified": None
    }
    
    timestamp = datetime.now(est).strftime("%Y-%m-%d %H:%M:%S")
    message = f'{interaction.user.mention} Logged Off: {timestamp}. \nWork Done: {work}'
    
    if attachment:
        await interaction.response.send_message(content=message, file=await attachment.to_file())
    else:
        await interaction.response.send_message(message)
    
    if interaction.user.id in users_to_remind:
        del users_to_remind[interaction.user.id]
    
    if interaction.user.id in users_on_break:
        del users_on_break[interaction.user.id]

@bot.tree.command(name="startbreak", description="Start a break and provide a reason.")
async def startbreak(interaction: discord.Interaction, reason: str):
    timestamp = datetime.now(est).strftime("%Y-%m-%d %H:%M:%S")
    message = f'{interaction.user.mention} Started a Break: {timestamp}. \nReason: {reason}'
    await interaction.response.send_message(message)
    users_on_break[interaction.user.id] = interaction.user
    user_status[interaction.user.id]["timestamp"] = datetime.now(est)
    

@bot.tree.command(name="endbreak", description="End your current break.")
async def endbreak(interaction: discord.Interaction):
    now = datetime.now(est)
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
    message = f'{interaction.user.mention} Ended their Break: {timestamp}.'
    await interaction.response.send_message(message)
    if interaction.user.id in users_on_break:
        del users_on_break[interaction.user.id]
    if interaction.user.id in user_status:
        user_status[interaction.user.id]["last_active"] = now 

@bot.tree.command(name="status", description="Check the status of users who are logged in and on a break.")
async def status(interaction: discord.Interaction):
    
    await interaction.response.defer()
    online_users = [user_id for user_id, status in user_status.items() if status["status"] == "online"]
    on_break_users = list(users_on_break.keys())
    
    message = ""
    
    if online_users:
        message += "Users currently logged in:\n"
        for i, user_id in enumerate(online_users, start=1):
            user = await bot.fetch_user(user_id)
            work = user_status[user_id]["work"]
            message += f'{i}. {user.mention} - Work: {work}\n'
    else:
        message += "No users are currently logged in.\n"
    
    if on_break_users:
        message += "\nUsers currently on a break:\n"
        for i, user_id in enumerate(on_break_users, start=1):
            user = await bot.fetch_user(user_id)
            message += f'{i}. {user.mention}\n'
    else:
        message += "\nNo users are currently on a break."
    
    await interaction.followup.send(message)

@bot.tree.command(name="help", description="List all available commands and their descriptions.")
async def help_command(interaction: discord.Interaction):
    commands = [
        "/logon - Log on and set your current work status.",
        "/logoff - Log off and set your work status to offline.",
        "/startbreak - Start a break and provide a reason.",
        "/endbreak - End your current break.",
        "/status - Check the status of users who are logged in and on a break.",
        "/work_summary - Get a summary of what each logged-in user is doing."
    ]
    message = "Here are the available commands:\n" + "\n".join(commands)
    await interaction.response.send_message(message, ephemeral=True)

@bot.tree.command(name="work_summary", description="Get a summary of what each logged-in user is doing.")
async def work_summary(interaction: discord.Interaction):
    
    await interaction.response.defer()
    online_users = [user_id for user_id, status in user_status.items() if status["status"] == "online"]
    
    if online_users:
        message = "Summary of logged-in users:\n"
        for i, user_id in enumerate(online_users, start=1):
            user = await bot.fetch_user(user_id)
            work = user_status[user_id]["work"]
            message += f'{i}. {user.mention} - Work: {work}\n'
    else:
        message = "No users are currently logged in."
    
    await interaction.followup.send(message)

@bot.tree.command(name="meeting_schedule", description="Schedule a meeting and notify participants.")
async def meeting_schedule(interaction: discord.Interaction, time: str, description: str, zoom_link: str = None, participants: str = None):
    try:
        participant_ids = participants.split() if participants else []
        message = f"Meeting scheduled for {time} with participants:\n"
        
        for participant_id in participant_ids:
            match = re.match(r'<@!?(\d+)>', participant_id)
            if match:
                user_id = int(match.group(1))
                user = await bot.fetch_user(user_id)
                message += f"{user.mention}\n"
        
        message += f"\nDescription: {description}"
        
        if zoom_link:
            if not zoom_link.startswith(('http://', 'https://')):
                zoom_link = 'https://' + zoom_link
            message += f"\nMeeting Link: {zoom_link}"
        
        await interaction.response.send_message(message, ephemeral=True)
        
        for participant_id in participant_ids:
            match = re.match(r'<@!?(\d+)>', participant_id)
            if match:
                user_id = int(match.group(1))
                user = await bot.fetch_user(user_id)
                dm_message = f"You have a meeting scheduled for {time}.\nDescription: {description}"
                if zoom_link:
                    dm_message += f"\nMeeting Link: {zoom_link}"
                try:
                    await user.send(dm_message)
                except discord.errors.HTTPException:
                    print(f"Cannot send DM to user {user_id}")
    except Exception as e:
        if not interaction.response.is_done():
            await interaction.response.send_message(f"An error occurred: {str(e)}", ephemeral=True)
        else:
            print(f"An error occurred: {str(e)}")

bot.run(os.getenv('BOT_ID'))
