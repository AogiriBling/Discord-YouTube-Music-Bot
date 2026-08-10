import discord
from discord import app_commands
from discord.ext import commands
import yt_dlp
import asyncio
import os
import ssl
import sys
import time
from typing import Optional


# this is for welcome bot, I thought to add in music bot - got bored.
WELCOME_CHANNEL_ID = 1530404114402643999

intents = discord.Intents.default()
intents.members = True

bot = discord.Client(intents=intents)

@bot.event
async def on_member_join(member):
    channel = bot.get_channel(WELCOME_CHANNEL_ID)
    if channel:
        message = await channel.send(f"Welcome {member.mention}! **Kindly read.**")
        await asyncio.sleep(2)
        await message.delete()


# MUSIC BOT STARTS FROM HERE XD

# Fix SSL certificate verification issue
ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE

# Monkey patch aiohttp to use our SSL context
import aiohttp
from aiohttp.connector import TCPConnector

original_init = TCPConnector.__init__

def new_init(self, *args, **kwargs):
    kwargs['ssl'] = ssl_context
    return original_init(self, *args, **kwargs)

TCPConnector.__init__ = new_init


class SearchView(discord.ui.View):
    """View for search results with selection buttons"""
    def __init__(self, results, user_id, guild_id, channel_id):
        super().__init__(timeout=None)  # Infinite timeout
        self.results = results
        self.user_id = user_id
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.selected_index = 0
        
        # Add buttons for each result with truncated titles
        for i, result in enumerate(results[:5], 1):
            # Truncate title to fit button label (max 80 chars)
            title = result['title']
            if len(title) > 75:
                title = title[:72] + "..."
            
            button = discord.ui.Button(
                label=f"{i}. {title}",
                style=discord.ButtonStyle.secondary,
                custom_id=f"search_{i}_{user_id}"
            )
            button.callback = self.create_callback(i-1)
            self.add_item(button)
        
        # Add cancel button
        cancel = discord.ui.Button(
            label="❌ Cancel",
            style=discord.ButtonStyle.danger,
            custom_id=f"search_cancel_{user_id}"
        )
        cancel.callback = self.cancel_callback
        self.add_item(cancel)
    
    def create_callback(self, index):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.user_id:
                embed = discord.Embed(
                    title="Error",
                    description="Only the person who searched can select a song!",
                    color=0xFFFFFF
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            self.selected_index = index
            await self.process_selection(interaction)
        return callback
    
    async def cancel_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            embed = discord.Embed(
                title="Error",
                description="Only the person who searched can cancel!",
                color=0xFFFFFF
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        embed = discord.Embed(
            title="Search Cancelled",
            description="No song was selected.",
            color=0xFFFFFF
        )
        await interaction.response.edit_message(embed=embed, view=None)
    
    async def process_selection(self, interaction: discord.Interaction):
        """Process the selected song"""
        result = self.results[self.selected_index]
        
        # Check if user is still in voice channel
        if not interaction.user.voice:
            embed = discord.Embed(
                title="Error",
                description="You need to be in a voice channel to play music!",
                color=0xFFFFFF
            )
            await interaction.response.edit_message(embed=embed, view=None)
            return
        
        # Update the message to show selection
        embed = discord.Embed(
            title="✅ Song Selected",
            description=f"**{result['title']}**\nAdding to queue...",
            color=0xFFFFFF
        )
        await interaction.response.edit_message(embed=embed, view=None)
        
        # Get the bot instance
        bot = interaction.client
        
        # Create song data
        song_data = {
            'url': result.get('webpage_url', result.get('original_url')),
            'title': result.get('title', 'Unknown Title'),
            'duration': result.get('duration'),
            'uploader': result.get('uploader', 'Unknown'),
            'requester_name': interaction.user.display_name,
            'request_channel_id': self.channel_id
        }
        
        try:
            # Get voice client with better error handling
            voice_client = interaction.guild.voice_client
            
            if not voice_client or not voice_client.is_connected():
                try:
                    voice_client = await bot.safe_voice_connect(interaction.user.voice.channel)
                except Exception as e:
                    embed = discord.Embed(
                        title="Voice Connection Error",
                        description=f"Failed to connect: {str(e)}",
                        color=0xFFFFFF
                    )
                    await interaction.followup.send(embed=embed, ephemeral=True)
                    return
                    
            elif voice_client.channel != interaction.user.voice.channel:
                try:
                    if voice_client.is_playing():
                        voice_client.stop()
                    await voice_client.disconnect()
                    await asyncio.sleep(0.5)
                    voice_client = await bot.safe_voice_connect(interaction.user.voice.channel)
                except Exception as e:
                    embed = discord.Embed(
                        title="Voice Connection Error",
                        description=f"Failed to move channels: {str(e)}",
                        color=0xFFFFFF
                    )
                    await interaction.followup.send(embed=embed, ephemeral=True)
                    return
            
            # Add to queue
            queue = bot.get_queue(self.guild_id)
            queue.append(song_data)
            
            # Start playing if nothing is playing
            if not voice_client.is_playing() and not voice_client.is_paused():
                await bot.play_next(self.guild_id, voice_client)
            else:
                # Send queue confirmation in the original channel
                channel = bot.get_channel(self.channel_id)
                embed = discord.Embed(
                    title="🎵 Added to Queue",
                    description=f"**{song_data['title']}**\nPosition in queue: {len(queue)}",
                    color=0xFFFFFF
                )
                await channel.send(embed=embed)
                
        except Exception as e:
            print(f"Error processing selection: {e}")
            channel = bot.get_channel(self.channel_id)
            embed = discord.Embed(
                title="Error",
                description=f"Failed to add song: {str(e)}",
                color=0xFFFFFF
            )
            await channel.send(embed=embed)


class MusicBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.voice_states = True
        
        super().__init__(command_prefix='!', intents=intents)
        self.server_id = 964856769312620574 # there is more than once this so replace it with ctrl + f
        self.commands_channel_id = 964867994209648691 # there is more than once this so replace it with ctrl + f
        
        # Track if commands have been synced
        self.commands_synced = False
        
        # Music queues and states for each guild
        self.queues = {}
        self.loop_states = {}
        self.now_playing = {}
        
        # YouTube DL configuration - with cookies support
        self.ytdl_format_options = {
            'format': 'bestaudio/best',
            'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
            'restrictfilenames': True,
            'noplaylist': True,
            'nocheckcertificate': True,
            'ignoreerrors': False,
            'logtostderr': False,
            'quiet': True,
            'no_warnings': True,
            'default_search': 'auto',
            'age_limit': 25,
            'extractor_args': {
                'youtube': {
                    'skip': ['dash', 'hls'],
                    'player_client': ['android', 'web']
                }
            },
        }

        # Fixed FFmpeg options
        self.ffmpeg_options = {
            'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
            'options': '-vn'
        }

        self.ytdl = yt_dlp.YoutubeDL(self.ytdl_format_options)
        self.voice_channel_check_task = None
        self.command_sync_task = None
        self.persistent_views_added = False
        self.reconnect_attempts = {}  # Track reconnect attempts per guild

    def get_queue(self, guild_id):
        """Get or create queue for a guild"""
        if guild_id not in self.queues:
            self.queues[guild_id] = []
        return self.queues[guild_id]
    
    def get_loop_state(self, guild_id):
        """Get or create loop state for a guild"""
        if guild_id not in self.loop_states:
            self.loop_states[guild_id] = False
        return self.loop_states[guild_id]
    
    def set_loop_state(self, guild_id, state):
        """Set loop state for a guild"""
        self.loop_states[guild_id] = state

    def get_now_playing(self, guild_id):
        """Get currently playing song"""
        return self.now_playing.get(guild_id)
    
    def set_now_playing(self, guild_id, song_data):
        """Set currently playing song"""
        self.now_playing[guild_id] = song_data

    async def setup_hook(self):
        """Setup hook for slash commands"""
        print("Running setup hook...")
        
        # Start the voice channel monitoring task
        self.voice_channel_check_task = self.loop.create_task(self.monitor_voice_channels())
        
        # Start command sync monitoring task
        self.command_sync_task = self.loop.create_task(self.periodic_command_sync())
        
        # Initial command sync
        await self.sync_commands()

    async def periodic_command_sync(self):
        """Periodically sync commands to ensure they stay active"""
        await self.wait_until_ready()
        while not self.is_closed():
            try:
                await asyncio.sleep(1800)  # 30 minutes
                
                if self.is_ready() and not self.commands_synced:
                    print("Periodic command sync check...")
                    await self.sync_commands()
            except Exception as e:
                print(f"Error in periodic_command_sync: {e}")
                await asyncio.sleep(300)

    async def sync_commands(self):
        """Sync slash commands"""
        try:
            guild = discord.Object(id=self.server_id)
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            self.commands_synced = True
            print(f"✅ Slash commands synced successfully! {len(synced)} commands available.")
            
        except discord.errors.HTTPException as e:
            print(f"⚠️ HTTP error syncing commands: {e}")
            self.commands_synced = False
        except Exception as e:
            print(f"⚠️ Error syncing commands: {e}")
            self.commands_synced = False
            await asyncio.sleep(60)
            await self.sync_commands()

    async def monitor_voice_channels(self):
        """Monitor voice channels and handle disconnections"""
        await self.wait_until_ready()
        while not self.is_closed():
            try:
                for voice_client in self.voice_clients:
                    if voice_client and voice_client.is_connected():
                        try:
                            members_in_vc = [member for member in voice_client.channel.members if not member.bot]
                            
                            if len(members_in_vc) == 0:
                                await asyncio.sleep(60)
                                if voice_client and voice_client.is_connected():
                                    members_in_vc_after = [member for member in voice_client.channel.members if not member.bot]
                                    if len(members_in_vc_after) == 0:
                                        commands_channel = self.get_channel(self.commands_channel_id)
                                        if commands_channel:
                                            embed = discord.Embed(
                                                title="Voice Channel Left",
                                                description="Left voice channel due to no one being in VC for 1 minute",
                                                color=0xFFFFFF
                                            )
                                            await commands_channel.send(embed=embed)
                                        guild_id = voice_client.guild.id
                                        if guild_id in self.queues:
                                            self.queues[guild_id].clear()
                                        if guild_id in self.loop_states:
                                            self.loop_states[guild_id] = False
                                        if guild_id in self.now_playing:
                                            del self.now_playing[guild_id]
                                        if voice_client.is_playing():
                                            voice_client.stop()
                                        await asyncio.sleep(1)
                                        await voice_client.disconnect(force=True)
                        except Exception as e:
                            print(f"Error checking members in VC: {e}")
            except Exception as e:
                print(f"Error in monitor_voice_channels: {e}")
            await asyncio.sleep(10)

    async def safe_voice_connect(self, voice_channel):
        """Safely connect to voice channel with multiple connection methods"""
        max_retries = 5
        last_error = None
        guild_id = voice_channel.guild.id
        
        # Initialize reconnect attempts counter
        if guild_id not in self.reconnect_attempts:
            self.reconnect_attempts[guild_id] = 0
        
        for attempt in range(max_retries):
            try:
                # Ensure we're not already connected
                if voice_channel.guild.voice_client:
                    try:
                        old_client = voice_channel.guild.voice_client
                        if old_client.is_playing():
                            old_client.stop()
                        await old_client.disconnect(force=True)
                        await asyncio.sleep(2)
                    except:
                        pass
                
                # Method 1: Try standard connection with increased timeout
                try:
                    voice_client = await asyncio.wait_for(
                        voice_channel.connect(timeout=30.0, reconnect=True, self_deaf=True),
                        timeout=35.0
                    )
                    
                    # Wait for connection to stabilize
                    await asyncio.sleep(3)
                    
                    if voice_client and voice_client.is_connected():
                        print(f"Successfully connected to voice channel using standard method")
                        self.reconnect_attempts[guild_id] = 0
                        
                        # Start heartbeat monitor
                        asyncio.create_task(self.monitor_voice_health(guild_id, voice_client))
                        
                        return voice_client
                except Exception as e:
                    print(f"Standard connection failed: {e}")
                    last_error = str(e)
                
                # Method 2: Try with different voice region if available
                if attempt == 2:  # Try region change on 3rd attempt
                    try:
                        # Force disconnect any existing connection
                        if voice_channel.guild.voice_client:
                            await voice_channel.guild.voice_client.disconnect(force=True)
                            await asyncio.sleep(3)
                        
                        # Try to connect with different parameters
                        voice_client = await voice_channel.connect(
                            timeout=30.0, 
                            reconnect=True, 
                            self_deaf=True,
                            cls=discord.VoiceClient
                        )
                        
                        await asyncio.sleep(3)
                        
                        if voice_client and voice_client.is_connected():
                            print(f"Successfully connected using alternative method")
                            self.reconnect_attempts[guild_id] = 0
                            asyncio.create_task(self.monitor_voice_health(guild_id, voice_client))
                            return voice_client
                    except Exception as e:
                        print(f"Alternative connection failed: {e}")
                        last_error = str(e)
                
                # Exponential backoff
                wait_time = min(2 ** attempt + (attempt * 1.5), 15)
                self.reconnect_attempts[guild_id] += 1
                print(f"Connection attempt {attempt + 1}/{max_retries} failed, retrying in {wait_time}s...")
                await asyncio.sleep(wait_time)
                
            except Exception as e:
                last_error = str(e)
                print(f"Connection error: {e}")
                wait_time = min(2 ** attempt + (attempt * 1.5), 15)
                await asyncio.sleep(wait_time)
        
        self.reconnect_attempts[guild_id] = 0
        raise Exception(f"Failed to connect after {max_retries} attempts: {last_error}")

    async def monitor_voice_health(self, guild_id, voice_client):
        """Monitor voice connection health"""
        consecutive_failures = 0
        while not self.is_closed():
            try:
                await asyncio.sleep(10)
                
                if not voice_client or not voice_client.is_connected():
                    print(f"Voice client disconnected for guild {guild_id}")
                    break
                
                # Try to ping the voice websocket
                try:
                    if hasattr(voice_client, 'ws') and voice_client.ws:
                        # Reset failure counter on successful check
                        consecutive_failures = 0
                except:
                    consecutive_failures += 1
                    if consecutive_failures >= 3:
                        print(f"Voice connection unhealthy for guild {guild_id}, attempting reconnect...")
                        await self.attempt_reconnect(guild_id)
                        break
                        
            except Exception as e:
                print(f"Error in voice health monitor: {e}")
                consecutive_failures += 1
                if consecutive_failures >= 3:
                    await self.attempt_reconnect(guild_id)
                    break

    async def attempt_reconnect(self, guild_id):
        """Attempt to reconnect to voice channel"""
        try:
            guild = self.get_guild(guild_id)
            if not guild:
                return
            
            # Find a voice channel with members
            target_channel = None
            for channel in guild.voice_channels:
                if len([m for m in channel.members if not m.bot]) > 0:
                    target_channel = channel
                    break
            
            if target_channel and guild_id in self.queues and self.queues[guild_id]:
                print(f"Attempting to reconnect to {target_channel.name} for guild {guild_id}")
                
                # Clean up old connection
                if guild.voice_client:
                    try:
                        if guild.voice_client.is_playing():
                            guild.voice_client.stop()
                        await guild.voice_client.disconnect(force=True)
                    except:
                        pass
                    await asyncio.sleep(2)
                
                # Connect to new channel
                voice_client = await self.safe_voice_connect(target_channel)
                
                # Resume playback
                if voice_client and voice_client.is_connected() and self.queues[guild_id]:
                    await self.play_next(guild_id, voice_client)
                    
        except Exception as e:
            print(f"Reconnection attempt failed for guild {guild_id}: {e}")

    async def cleanup_voice_client(self, guild_id):
        """Clean up voice client state"""
        guild = self.get_guild(guild_id)
        if guild and guild.voice_client:
            try:
                if guild.voice_client.is_playing():
                    guild.voice_client.stop()
                await guild.voice_client.disconnect(force=True)
            except:
                pass
            await asyncio.sleep(0.5)

    async def play_next(self, guild_id, voice_client):
        """Play the next song in the queue"""
        try:
            queue = self.get_queue(guild_id)
            loop_state = self.get_loop_state(guild_id)
            
            if loop_state and self.get_now_playing(guild_id):
                current_song = self.get_now_playing(guild_id)
                await self.play_song(guild_id, voice_client, current_song)
                return
            
            if queue:
                song_data = queue.pop(0)
                await self.play_song(guild_id, voice_client, song_data)
            else:
                self.set_loop_state(guild_id, False)
                self.set_now_playing(guild_id, None)
        except Exception as e:
            print(f"Error in play_next: {e}")

    async def play_song(self, guild_id, voice_client, song_data):
        """Play a specific song"""
        try:
            audio_url = await self.get_audio_url(song_data['url'])
            
            if not audio_url:
                print("Failed to get audio URL")
                await self.play_next(guild_id, voice_client)
                return
            
            audio_source = discord.FFmpegPCMAudio(
                audio_url,
                **self.ffmpeg_options
            )
            
            audio_source = discord.PCMVolumeTransformer(audio_source, volume=0.5)
            
            def after_playing(error):
                if error:
                    print(f'Player error: {error}')
                coro = self.play_next(guild_id, voice_client)
                asyncio.run_coroutine_threadsafe(coro, self.loop)
            
            if voice_client.is_playing():
                voice_client.stop()
                await asyncio.sleep(0.5)
            
            voice_client.play(audio_source, after=after_playing)
            self.set_now_playing(guild_id, song_data)
            
            channel = self.get_channel(song_data['request_channel_id'])
            if channel:
                embed = discord.Embed(
                    title="🎵 Now Playing",
                    description=f"**{song_data['title']}**",
                    color=0xFFFFFF
                )
                if song_data.get('duration'):
                    duration = song_data['duration']
                    embed.add_field(name="Duration", value=f"{duration//60}:{duration%60:02d}", inline=True)
                if song_data.get('uploader'):
                    embed.add_field(name="Uploader", value=song_data['uploader'], inline=True)
                
                if self.get_loop_state(guild_id):
                    embed.add_field(name="Loop", value="🔁 Enabled", inline=True)
                
                embed.set_footer(text=f"Requested by {song_data['requester_name']}")
                await channel.send(embed=embed)
                
        except Exception as e:
            print(f"Error playing song: {e}")
            await self.play_next(guild_id, voice_client)

    async def get_audio_url(self, url):
        """Extract direct audio URL from YouTube"""
        try:
            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(None, lambda: self.ytdl.extract_info(url, download=False))
            
            if 'entries' in data:
                data = data['entries'][0]
            
            if 'url' in data:
                return data['url']
            else:
                for format in data.get('formats', []):
                    if format.get('acodec') != 'none' and format.get('vcodec') == 'none':
                        return format['url']
                
                for format in data.get('formats', []):
                    if format.get('url'):
                        return format['url']
                        
        except Exception as e:
            print(f"Error getting audio URL: {e}")
        
        return None

# Initialize bot
bot = MusicBot()

@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')
    print(f'Bot is in {len(bot.guilds)} guild(s)')
    
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.listening, 
            name="ZapBot | /play"
        )
    )
    
    if not bot.commands_synced:
        print("Commands not synced, attempting to sync now...")
        await bot.sync_commands()

@bot.event
async def on_resumed():
    print("Bot has resumed connection")
    await bot.sync_commands()

@bot.event
async def on_guild_available(guild):
    if guild.id == bot.server_id:
        print(f"Guild {guild.name} is now available")
        await bot.sync_commands()

@bot.event
async def on_voice_state_update(member, before, after):
    if member == bot.user:
        if before.channel and after.channel and before.channel != after.channel:
            print(f"Bot moved from {before.channel.name} to {after.channel.name}")
    
    if member == bot.user and before.channel and not after.channel:
        print("Bot was disconnected from voice channel")
        guild_id = before.channel.guild.id
        
        # Attempt to reconnect if there's still music to play
        if guild_id in bot.queues and bot.queues[guild_id]:
            print(f"Attempting to reconnect for guild {guild_id} due to queued songs...")
            await bot.attempt_reconnect(guild_id)
        else:
            # Clear state if no songs to play
            if guild_id in bot.queues:
                bot.queues[guild_id].clear()
            if guild_id in bot.loop_states:
                bot.loop_states[guild_id] = False
            if guild_id in bot.now_playing:
                del bot.now_playing[guild_id]

@bot.tree.command(name="play", description="Play a song from YouTube")
@app_commands.describe(query="Song name or YouTube URL")
async def play_slash(interaction: discord.Interaction, query: str):
    if not interaction.user.voice:
        embed = discord.Embed(
            title="Error",
            description="You need to be in a voice channel to play music!",
            color=0xFFFFFF
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    await interaction.response.defer()
    
    try:
        # Extract video info
        loop = asyncio.get_event_loop()
        search_data = await loop.run_in_executor(None, lambda: bot.ytdl.extract_info(f"ytsearch5:{query}", download=False))
        
        search_results = search_data.get('entries', []) if 'entries' in search_data else [search_data]
        
        if not search_results:
            embed = discord.Embed(
                title="No Results Found",
                description="No videos found for your search query.",
                color=0xFFFFFF
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        
        # Create embed with search results (truncated for display)
        description = ""
        for i, result in enumerate(search_results[:5], 1):
            title = result.get('title', 'Unknown Title')
            if len(title) > 50:
                title = title[:47] + "..."
            duration = result.get('duration')
            duration_str = f" ({duration//60}:{duration%60:02d})" if duration else ""
            description += f"**{i}.** {title}{duration_str}\n"
        
        embed = discord.Embed(
            title="🔍 Search Results",
            description=description,
            color=0xFFFFFF
        )
        embed.set_footer(text=f"Select a song below | Buttons never expire")
        
        # Create view with buttons
        view = SearchView(
            search_results[:5], 
            interaction.user.id, 
            interaction.guild_id, 
            interaction.channel_id
        )
        
        await interaction.followup.send(embed=embed, view=view)
        
    except Exception as e:
        print(f"Play command error: {e}")
        embed = discord.Embed(
            title="Search Error",
            description="Failed to search for songs. Please try again.",
            color=0xFFFFFF
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

@bot.tree.command(name="queue", description="Show the current music queue")
async def queue_slash(interaction: discord.Interaction):
    queue = bot.get_queue(interaction.guild.id)
    loop_state = bot.get_loop_state(interaction.guild.id)
    now_playing = bot.get_now_playing(interaction.guild.id)
    
    embed = discord.Embed(title="🎵 Music Queue", color=0xFFFFFF)
    
    if now_playing:
        embed.add_field(
            name="Now Playing",
            value=f"**{now_playing['title']}**\n👤 {now_playing['requester_name']}",
            inline=False
        )
    
    if queue:
        description = ""
        for i, song in enumerate(queue[:10], 1):
            duration = f" ({song['duration']//60}:{song['duration']%60:02d})" if song.get('duration') else ""
            description += f"**{i}. {song['title']}**{duration}\n"
            description += f"   👤 {song['requester_name']}\n\n"
        
        if len(queue) > 10:
            description += f"... and {len(queue) - 10} more songs"
        
        embed.add_field(name="Up Next", value=description, inline=False)
    else:
        embed.add_field(
            name="Queue",
            value="No songs in queue. Use `/play` to add some!",
            inline=False
        )
    
    loop_status = "🔁 **Enabled**" if loop_state else "➡️ **Disabled**"
    embed.add_field(name="Loop Mode", value=loop_status, inline=True)
    embed.add_field(name="Total Songs", value=str(len(queue)), inline=True)
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="loop", description="Toggle loop for the current song")
async def loop_slash(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client
    
    if not voice_client or not voice_client.is_connected():
        embed = discord.Embed(
            title="Error",
            description="I'm not connected to a voice channel!",
            color=0xFFFFFF
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    if not voice_client.is_playing() and not voice_client.is_paused():
        embed = discord.Embed(
            title="Error",
            description="No audio is currently playing!",
            color=0xFFFFFF
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    current_loop = bot.get_loop_state(interaction.guild.id)
    new_loop_state = not current_loop
    bot.set_loop_state(interaction.guild.id, new_loop_state)
    
    if new_loop_state:
        embed = discord.Embed(
            title="🔁 Loop Enabled",
            description="Current song will now loop continuously",
            color=0xFFFFFF
        )
    else:
        embed = discord.Embed(
            title="➡️ Loop Disabled",
            description="Loop has been turned off",
            color=0xFFFFFF
        )
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="pause", description="Pause the current song")
async def pause_slash(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client
    
    if not voice_client or not voice_client.is_connected():
        embed = discord.Embed(
            title="Error",
            description="I'm not connected to a voice channel!",
            color=0xFFFFFF
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    if voice_client.is_playing():
        voice_client.pause()
        embed = discord.Embed(
            title="⏸️ Paused",
            description="The current song has been paused",
            color=0xFFFFFF
        )
        await interaction.response.send_message(embed=embed)
    else:
        embed = discord.Embed(
            title="Error",
            description="No audio is currently playing!",
            color=0xFFFFFF
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="resume", description="Resume the paused song")
async def resume_slash(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client
    
    if not voice_client or not voice_client.is_connected():
        embed = discord.Embed(
            title="Error",
            description="I'm not connected to a voice channel!",
            color=0xFFFFFF
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    if voice_client.is_paused():
        voice_client.resume()
        embed = discord.Embed(
            title="▶️ Resumed",
            description="The song has been resumed",
            color=0xFFFFFF
        )
        await interaction.response.send_message(embed=embed)
    else:
        embed = discord.Embed(
            title="Error",
            description="Audio is not paused!",
            color=0xFFFFFF
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="skip", description="Skip the current song")
async def skip_slash(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client
    
    if not voice_client or not voice_client.is_connected():
        embed = discord.Embed(
            title="Error",
            description="I'm not connected to a voice channel!",
            color=0xFFFFFF
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    if voice_client.is_playing() or voice_client.is_paused():
        voice_client.stop()
        embed = discord.Embed(
            title="⏭️ Skipped",
            description=f"The song has been skipped by {interaction.user.mention}",
            color=0xFFFFFF
        )
        await interaction.response.send_message(embed=embed)
    else:
        embed = discord.Embed(
            title="Error",
            description="No audio is currently playing!",
            color=0xFFFFFF
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="stop", description="Stop the music and clear the queue")
async def stop_slash(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client
    
    if not voice_client or not voice_client.is_connected():
        embed = discord.Embed(
            title="Error",
            description="I'm not connected to a voice channel!",
            color=0xFFFFFF
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    if voice_client.is_playing() or voice_client.is_paused():
        voice_client.stop()
    
    guild_id = interaction.guild.id
    if guild_id in bot.queues:
        bot.queues[guild_id].clear()
    if guild_id in bot.loop_states:
        bot.loop_states[guild_id] = False
    if guild_id in bot.now_playing:
        del bot.now_playing[guild_id]
    
    embed = discord.Embed(
        title="⏹️ Stopped",
        description="Music stopped and queue cleared",
        color=0xFFFFFF
    )
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="disconnect", description="Disconnect the bot from voice channel")
async def disconnect_slash(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client
    
    if not voice_client or not voice_client.is_connected():
        embed = discord.Embed(
            title="Error",
            description="I'm not connected to a voice channel!",
            color=0xFFFFFF
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    if voice_client.is_playing() or voice_client.is_paused():
        voice_client.stop()
    
    guild_id = interaction.guild.id
    if guild_id in bot.queues:
        bot.queues[guild_id].clear()
    if guild_id in bot.loop_states:
        bot.loop_states[guild_id] = False
    if guild_id in bot.now_playing:
        del bot.now_playing[guild_id]
    
    await voice_client.disconnect(force=True)
    
    embed = discord.Embed(
        title="👋 Disconnected",
        description="Left the voice channel",
        color=0xFFFFFF
    )
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="ping", description="Check if bot is responsive")
async def ping_slash(interaction: discord.Interaction):
    latency = round(bot.latency * 1000)
    
    embed = discord.Embed(
        title="🏓 Pong!",
        description=f"Bot latency: **{latency}ms**",
        color=0xFFFFFF
    )
    embed.add_field(name="Commands Status", 
                   value="✅ Active" if bot.commands_synced else "⚠️ Syncing...",
                   inline=True)
    embed.add_field(name="Voice Clients", 
                   value=f"{len(bot.voice_clients)} connected",
                   inline=True)
    
    await interaction.response.send_message(embed=embed)

# Run the bot
if __name__ == "__main__":
    bot.server_id = 964856769312620574 # there is more than once this so replace it with ctrl + f
    bot.commands_channel_id = 964867994209648691 # there is more than once this so replace it with ctrl + f
    
    NEW_TOKEN = "your token goes here"
    
    try:
        bot.run(NEW_TOKEN, reconnect=True)
    except KeyboardInterrupt:
        print("Bot stopped by user")
    except Exception as e:
        print(f"Bot crashed: {e}")
        print("Restarting in 5 seconds...")
        import time
        time.sleep(5)
        os.execv(sys.executable, ['python'] + sys.argv)
