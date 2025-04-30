import discord
from discord import app_commands
from discord.ext import commands
from discord.utils import get
from discord.ui import Button, View
import requests
import os
import logging
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_fixed

from db import (
    init_db,
    load_guild_setup,
    save_guild_setup,
    load_user_data,
    save_user_data
)

logging.basicConfig(
    filename="bot.log",
    level=logging.INFO,
    format="%(asctime)s:%(levelname)s:%(message)s"
)

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
SERVER = os.getenv("SERVER") or "Asia"
ERROR_WEBHOOK_URL = os.getenv("ERROR_WEBHOOK_URL")

intents = discord.Intents.default()
intents.members = True

bot = commands.Bot(command_prefix='/', intents=intents)
tree = bot.tree

async def send_error_webhook(error, command, guild_id):
    if ERROR_WEBHOOK_URL:
        try:
            embed = discord.Embed(title="Bot Error", color=discord.Color.red())
            embed.add_field(name="Command", value=command, inline=False)
            embed.add_field(name="Guild ID", value=guild_id or "N/A", inline=False)
            embed.add_field(name="Error", value=str(error)[:1000], inline=False)
            requests.post(ERROR_WEBHOOK_URL, json={"embeds": [embed.to_dict()]})
        except Exception as e:
            logging.error(f"Failed to send error webhook: {str(e)}")

@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
def find_guild_by_name(guild_name):
    url = f"https://gameinfo-sgp.albiononline.com/api/gameinfo/search?q={guild_name}"
    res = requests.get(url, timeout=10)
    res.raise_for_status()
    return res.json().get('guilds', [])

@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
def guild_member_list(guild_id):
    url = f"https://gameinfo-sgp.albiononline.com/api/gameinfo/guilds/{guild_id}/members"
    res = requests.get(url, timeout=10)
    res.raise_for_status()
    return res.json()

@bot.event
async def on_ready():
    init_db()
    logging.info(f"Logged in as {bot.user}")
    print(f"  Logged in as {bot.user}")
    try:
        await tree.sync()
        print("  Synced global slash commands")
    except Exception as e:
        print(f" Sync failed: {e}")

@tree.command(name="check_guild", description="ค้นหา token_ID ของกิลด์ใน Albion Online")
@app_commands.describe(guild_name="ชื่อกิลด์ในเกม Albion Online")
async def check_guild(interaction: discord.Interaction, guild_name: str):
    try:
        guilds = find_guild_by_name(guild_name)
        if guilds:
            response = "🎯 **พบข้อมูลกิลด์:**\n"
            for guild in guilds:
                response += f"- ชื่อ: `{guild['Name']}` | token_ID: `{guild['Id']}`\n"
            await interaction.response.send_message(response)
        else:
            await interaction.response.send_message(f" ไม่พบกิลด์ชื่อ `{guild_name}`", ephemeral=True)
    except Exception as e:
        logging.error(f"Error in check_guild for guild_id {interaction.guild_id}: {str(e)}")
        await send_error_webhook(e, "check_guild", interaction.guild_id)
        await interaction.response.send_message(f"  เกิดข้อผิดพลาด: {str(e)}", ephemeral=True)

@tree.command(name="add_guild", description="ตั้งค่ากิลด์จากชื่อกิลด์ และกำหนดยศ Discord (สำหรับผู้ดูแล)")
@app_commands.describe(
    guild_name="ชื่อกิลด์ในเกม Albion Online",
    role_name="ชื่อ Role ที่จะมอบให้"
)
async def add_guild(interaction: discord.Interaction, guild_name: str, role_name: str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("  เฉพาะผู้ดูแลเซิร์ฟเวอร์เท่านั้นที่ใช้คำสั่งนี้ได้", ephemeral=True)
        return

    guild_setup = load_guild_setup(interaction.guild_id)
    try:
        guilds = find_guild_by_name(guild_name)
        matched = [g for g in guilds if g["Name"].lower() == guild_name.lower()]

        if not matched:
            await interaction.response.send_message(f"  ไม่พบกิลด์ชื่อ `{guild_name}`", ephemeral=True)
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

        if not role:
            await interaction.response.send_message(f"  ไม่พบ Role ชื่อ `{role_name}` ใน Discord", ephemeral=True)
            return

        if role.position >= interaction.guild.me.top_role.position:
            await interaction.response.send_message(
                f"บอทไม่มีสิทธิ์จัดการ Role `{role.name}` กรุณาย้ายบทบาทของบอทให้สูงกว่า Role นี้ใน Server Settings > Roles",
                ephemeral=True
            )
            return

        guild_setup['guild_token'] = token_id
        guild_setup['guild_name'] = guild_name_real
        guild_setup['discord_role'] = role.name
        save_guild_setup(interaction.guild_id, guild_setup)
        await interaction.response.send_message(
            f"ตั้งค่ากิลด์สำเร็จ:\n"
            f"- Guild: `{guild_name_real}`\n"
            f"- ID: `{token_id}`\n"
            f"- Role: `{role.name}`"
        )
        logging.info(f"Guild setup updated for guild_id {interaction.guild_id}: {guild_name_real}")
    except Exception as e:
        logging.error(f"Error in add_guild for guild_id {interaction.guild_id}: {str(e)}")
        await send_error_webhook(e, "add_guild", interaction.guild_id)
        await interaction.response.send_message(f"เกิดข้อผิดพลาด: {str(e)}", ephemeral=True)

@tree.command(name="register", description="ลงทะเบียนชื่อในเกม Albion Online")
@app_commands.describe(ign="ชื่อในเกมของคุณ")
async def register(interaction: discord.Interaction, ign: str):
    guild_setup = load_guild_setup(interaction.guild_id)
    user_data = load_user_data(interaction.guild_id)

    if guild_setup["guild_token"] is None or guild_setup["discord_role"] is None:
        await interaction.response.send_message("กรุณาตั้งค่า guild และ role ก่อนใช้งาน!", ephemeral=True)
        return

    try:
        member_list = guild_member_list(guild_setup["guild_token"])
        found = next((m for m in member_list if m['Name'].lower() == ign.lower()), None)

        if not found:
            await interaction.response.send_message(f"ไม่พบผู้เล่น `{ign}` ในกิลด์ `{guild_setup['guild_name']}`", ephemeral=True)
            return

        for uid, data in list(user_data.items()):
            if data['ign'].lower() == ign.lower():
                member = await interaction.guild.fetch_member(uid)
                role = get(interaction.guild.roles, name=guild_setup['discord_role'])
                if not member or not role or role not in member.roles:
                    user_data.pop(uid)
                else:
                    await interaction.response.send_message("  ชื่อนี้ถูกใช้งานโดย Discord อื่นแล้ว", ephemeral=True)
                    return

        if interaction.user.id in user_data:
            await interaction.response.send_message("⚠️ คุณเคยลงทะเบียนไปแล้ว!", ephemeral=True)
            return

        role = get(interaction.guild.roles, name=guild_setup['discord_role'])
        if not role:
            await interaction.response.send_message(f"  ไม่พบยศ `{guild_setup['discord_role']}` ใน Discord", ephemeral=True)
            return

        if role.position >= interaction.guild.me.top_role.position:
            await interaction.response.send_message(
                f"บอทไม่มีสิทธิ์จัดการ Role `{role.name}` กรุณาย้ายบทบาทของบอทให้สูงกว่า Role นี้ใน Server Settings > Roles",
                ephemeral=True
            )
            return

        try:
            await interaction.user.add_roles(role)
        except discord.errors.Forbidden as e:
            logging.error(f"Failed to add role {role.name} to user {interaction.user.id}: {str(e)}")
            await interaction.response.send_message(
                f"บอทไม่มีสิทธิ์เพิ่ม Role `{role.name}` กรุณาตรวจสอบสิทธิ์หรือลำดับบทบาทของบอท",
                ephemeral=True
            )
            return

        user_data[interaction.user.id] = {"ign": ign}
        save_user_data(interaction.guild_id, user_data)
        await interaction.response.send_message(f"  ลงทะเบียนสำเร็จ IGN: `{ign}` คุณได้รับยศ `{role.name}` แล้ว")
        logging.info(f"User {interaction.user.id} registered IGN {ign} in guild_id {interaction.guild_id}")
    except Exception as e:
        logging.error(f"Error in register for guild_id {interaction.guild_id}: {str(e)}")
        await send_error_webhook(e, "register", interaction.guild_id)
        await interaction.response.send_message(f"  เกิดข้อผิดพลาด: {str(e)}", ephemeral=True)

@tree.command(name="remove_user", description="ลบผู้ใช้ที่เคยลงทะเบียน (เฉพาะผู้ดูแลเท่านั้น)")
@app_commands.describe(user="เลือกผู้ใช้ที่ต้องการลบ")
async def remove_user(interaction: discord.Interaction, user: discord.Member):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("เฉพาะผู้ดูแลเซิร์ฟเวอร์เท่านั้นที่ใช้คำสั่งนี้ได้", ephemeral=True)
        return

    user_data = load_user_data(interaction.guild_id)
    if user.id not in user_data:
        await interaction.response.send_message("ผู้ใช้นี้ยังไม่ได้ลงทะเบียน", ephemeral=True)
        return

    view = View(timeout=30)

    confirm_button = Button(label="✅ ยืนยัน", style=discord.ButtonStyle.danger)
    cancel_button = Button(label="❌ ยกเลิก", style=discord.ButtonStyle.secondary)

    async def confirm_callback(button_interaction: discord.Interaction):
        if button_interaction.user.id != interaction.user.id:
            await button_interaction.response.send_message("คุณไม่มีสิทธิ์กดยืนยัน", ephemeral=True)
            return
        try:
            guild_setup = load_guild_setup(interaction.guild_id)
            role_name = guild_setup.get("discord_role")
            if role_name:
                role = get(interaction.guild.roles, name=role_name)
                if role and role in user.roles:
                    await user.remove_roles(role)

            user_data.pop(user.id)
            save_user_data(interaction.guild_id, user_data)

            await button_interaction.response.edit_message(
                content=f"✅ ลบผู้ใช้ `{user.display_name}` สำเร็จแล้ว",
                view=None
            )
            logging.info(f"Admin {interaction.user.id} removed user {user.id} from guild {interaction.guild_id}")
        except Exception as e:
            logging.error(f"Error in remove_user for guild_id {interaction.guild_id}: {str(e)}")
            await send_error_webhook(e, "remove_user", interaction.guild_id)
            await button_interaction.response.edit_message(
                content=f"เกิดข้อผิดพลาด: {str(e)}",
                view=None
            )

    async def cancel_callback(button_interaction: discord.Interaction):
        if button_interaction.user.id != interaction.user.id:
            await button_interaction.response.send_message("คุณไม่มีสิทธิ์กดยกเลิก", ephemeral=True)
            return
        await button_interaction.response.edit_message(content="ยกเลิกการลบผู้ใช้แล้ว", view=None)

    confirm_button.callback = confirm_callback
    cancel_button.callback = cancel_callback

    view.add_item(confirm_button)
    view.add_item(cancel_button)

    await interaction.response.send_message(
        f"คุณต้องการลบผู้ใช้ `{user.display_name}` ออกจากระบบหรือไม่?",
        view=view,
        ephemeral=True
    )



@tree.command(name="reset", description="รีเซ็ตการตั้งค่ากิลด์ (สำหรับผู้ดูแลเท่านั้น)")
async def reset(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("เฉพาะผู้ดูแลเซิร์ฟเวอร์เท่านั้นที่ใช้คำสั่งนี้ได้", ephemeral=True)
        return

    view = View()
    confirm_button = Button(label="ยืนยันรีเซ็ต", style=discord.ButtonStyle.danger)

    async def confirm_callback(interaction: discord.Interaction):
        try:
            guild_setup = load_guild_setup(interaction.guild_id)
            guild_setup['guild_token'] = None
            guild_setup['guild_name'] = None
            guild_setup['discord_role'] = None
            guild_setup['server'] = SERVER
            save_guild_setup(interaction.guild_id, guild_setup)
            await interaction.response.edit_message(content="รีเซ็ตการตั้งค่ากิลด์เรียบร้อยแล้ว", view=None)
            logging.info(f"Guild setup reset for guild_id {interaction.guild_id}")
        except Exception as e:
            logging.error(f"Error in reset for guild_id {interaction.guild_id}: {str(e)}")
            await send_error_webhook(e, "reset", interaction.guild_id)
            await interaction.response.edit_message(content=f"เกิดข้อผิดพลาด: {str(e)}", view=None)

    confirm_button.callback = confirm_callback
    view.add_item(confirm_button)
    await interaction.response.send_message(
        "คุณแน่ใจว่าต้องการรีเซ็ตการตั้งค่ากิลด์หรือไม่? คลิกปุ่มเพื่อยืนยัน",
        view=view,
        ephemeral=True
    )

@bot.event
async def on_member_remove(member):
    try:
        user_data = load_user_data(member.guild.id)
        if member.id in user_data:
            user_data.pop(member.id, None)
            save_user_data(member.guild.id, user_data)
            logging.info(f"User {member.name} removed from guild_id {member.guild.id}")
            print(f" {member.name} ออกจาก Discord แล้ว ข้อมูลถูกลบ")
    except Exception as e:
        logging.error(f"Error in on_member_remove for guild_id {member.guild.id}: {str(e)}")
        await send_error_webhook(e, "on_member_remove", member.guild.id)

@tree.command(name="sync", description="Sync คำสั่ง Slash Command (สำหรับผู้ดูแล)")
async def sync(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("  เฉพาะผู้ดูแลเซิร์ฟเวอร์เท่านั้นที่ใช้คำสั่งนี้ได้", ephemeral=True)
        return
    try:
        await tree.sync(guild=discord.Object(id=interaction.guild_id))
        await interaction.response.send_message("  คำสั่งถูก sync เรียบร้อยแล้ว", ephemeral=True)
        logging.info(f"Commands synced by {interaction.user.id} in guild_id {interaction.guild_id}")
    except Exception as e:
        logging.error(f"Error in sync for guild_id {interaction.guild_id}: {str(e)}")
        await send_error_webhook(e, "sync", interaction.guild_id)
        await interaction.response.send_message(f"  เกิดข้อผิดพลาด: {str(e)}", ephemeral=True)

try:
    bot.run(TOKEN)
except discord.errors.LoginFailure as e:
    logging.error(f"Failed to login: {str(e)}")
    print(f" Failed to login: {str(e)}")
except Exception as e:
    logging.error(f"Unexpected error: {str(e)}")
    print(f" Unexpected error: {str(e)}")