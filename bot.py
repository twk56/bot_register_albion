import discord
from discord import app_commands
from discord.ext import commands
from discord.utils import get
import requests
import os
from dotenv import load_dotenv

load_dotenv()

intents = discord.Intents.default()
intents.members = True

bot = commands.Bot(command_prefix='/', intents=intents)
tree = bot.tree

TOKEN = os.getenv("DISCORD_TOKEN")
SERVER = os.getenv("SERVER") or "Asia"

guild_setup = {
    "guild_token": None,
    "guild_name": None,
    "discord_role": None,
    "server": SERVER
}

user_data = {}

def find_guild_by_name(guild_name):
    url = f"https://gameinfo-sgp.albiononline.com/api/gameinfo/search?q={guild_name}"
    res = requests.get(url).json()
    return res.get('guilds', [])

def guild_member_list(guild_id):
    
    url = f"https://gameinfo-sgp.albiononline.com/api/gameinfo/guilds/{guild_id}/members"
    res = requests.get(url).json()
    return res

@bot.event
async def on_ready():
    await tree.sync()
    print(f"✅ Logged in as {bot.user}")

@tree.command(name="check_guild", description="ค้นหา token_ID ของกิลด์ใน Albion Online")
@app_commands.describe(guild_name="ชื่อกิลด์ในเกม Albion Online")
async def check_guild(interaction: discord.Interaction, guild_name: str):
    guilds = find_guild_by_name(guild_name)
    if guilds:
        response = "🎯 **พบข้อมูลกิลด์:**\n"
        for guild in guilds:
            response += f"- ชื่อ: `{guild['Name']}` | token_ID: `{guild['Id']}`\n"
        await interaction.response.send_message(response)
    else:
        await interaction.response.send_message(f"❌ ไม่พบกิลด์ชื่อ `{guild_name}`", ephemeral=True)

@tree.command(name="add_guild", description="ตั้งค่ากิลด์จากชื่อกิลด์ และกำหนดยศ Discord")
@app_commands.describe(
    guild_name="ชื่อกิลด์ในเกม Albion Online",
    role_name="ชื่อ Role ที่จะมอบให้"
)
async def add_guild(interaction: discord.Interaction, guild_name: str, role_name: str):
    try:
        url = f"https://gameinfo-sgp.albiononline.com/api/gameinfo/search?q={guild_name}"
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            await interaction.response.send_message("❌ ไม่สามารถติดต่อ API ได้", ephemeral=True)
            return

        data = response.json()
        guilds = data.get("guilds", [])
        matched = [g for g in guilds if g["Name"].lower() == guild_name.lower()]

        if not matched:
            await interaction.response.send_message(f"❌ ไม่พบกิลด์ชื่อ `{guild_name}`", ephemeral=True)
            return

        guild_info = matched[0]
        token_id = guild_info["Id"]
        guild_name_real = guild_info["Name"]

        role = None
        if role_name.startswith("<@&") and role_name.endswith(">"):
            role_id = int(role_name[3:-1])
            role = interaction.guild.get_role(role_id)
        elif role_name.isdigit():
            role = interaction.guild.get_role(int(role_name))
        else:
            role = get(interaction.guild.roles, name=role_name)

        if role:
            guild_setup['guild_token'] = token_id
            guild_setup['guild_name'] = guild_name_real
            guild_setup['discord_role'] = role.name
            await interaction.response.send_message(
                f"Guild: `{guild_name_real}`\n"
                f"ID: `{token_id}`\n"
                f"Role: `{role.name}`"
            )
        else:
            await interaction.response.send_message(f"❌ ไม่พบ Role ชื่อ `{role_name}` ใน Discord", ephemeral=True)

    except Exception as e:
        await interaction.response.send_message(f"❌ เกิดข้อผิดพลาด: {str(e)}", ephemeral=True)



@tree.command(name="register", description="ลงทะเบียนชื่อในเกม Albion Online")
@app_commands.describe(ign="ชื่อในเกมของคุณ")
async def register(interaction: discord.Interaction, ign: str):
    if guild_setup["guild_token"] is None or guild_setup["discord_role"] is None:
        await interaction.response.send_message("⚠️ กรุณาตั้งค่า guild และ role ก่อนใช้งาน!", ephemeral=True)
        return

    member_list = guild_member_list(guild_setup["guild_token"])
    found = next((m for m in member_list if m['Name'].lower() == ign.lower()), None)

    
    if found:
        if ign.lower() in (data['ign'].lower() for data in user_data.values()):
            await interaction.response.send_message("ชื่อนี้ถูกใช้งานโดย Discord อื่นแล้ว", ephemeral=True)
            return

        if interaction.user.id in user_data:
            await interaction.response.send_message("⚠️ คุณเคยลงทะเบียนไปแล้ว!", ephemeral=True)
            return

        role = get(interaction.guild.roles, name=guild_setup['discord_role'])
        if role:
            await interaction.user.add_roles(role)
            user_data[interaction.user.id] = {"ign": ign}
            await interaction.response.send_message(f"✅ ลงทะเบียนสำเร็จ IGN: `{ign}` คุณได้รับยศ `{role.name}` แล้ว")
        else:
            await interaction.response.send_message(f"❌ ไม่พบยศ `{guild_setup['discord_role']}` ใน Discord", ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ ไม่พบผู้เล่น `{ign}` ในกิลด์ `{guild_setup['guild_name']}`", ephemeral=True)

@bot.event
async def on_member_remove(member):
    if member.id in user_data:
        user_data.pop(member.id, None)
        print(f"❌ {member.name} ออกจาก Discord แล้ว ข้อมูลถูกลบ")

bot.run(TOKEN)
