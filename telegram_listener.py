"""
Telegram Listener for betting signals.
Monitors specified channels/groups/chats and parses betting signals.
"""

import re
import os
import asyncio
import threading
from datetime import datetime
from typing import Optional, Callable, Dict, List
from telethon import TelegramClient, events
from telethon.sessions import StringSession


class TelegramListener:
    """Listens to Telegram messages and triggers bet placement."""
    
    def __init__(self, api_id: int, api_hash: str, session_string: str = None, session_path: str = None):
        """
        Initialize Telegram listener.
        
        Args:
            api_id: Telegram API ID (from my.telegram.org)
            api_hash: Telegram API Hash
            session_string: Optional saved session string for persistent login
            session_path: Optional path to session file (preferred over session_string)
        """
        self.api_id = api_id
        self.api_hash = api_hash
        self.session_string = session_string
        self.session_path = session_path
        self.client: Optional[TelegramClient] = None
        self.running = False
        self.loop = None
        self.thread = None
        
        self.monitored_chats: List[int] = []
        self.signal_callback: Optional[Callable] = None
        self.message_callback: Optional[Callable] = None
        self.status_callback: Optional[Callable] = None
        
        self.signal_patterns = self._default_patterns()
    
    def _default_patterns(self) -> Dict:
        """Default regex patterns for parsing betting signals."""
        return {
            'event': r'🆚\s*(.+?)(?:\n|$)',
            'league': r'🏆\s*(.+?)(?:\n|$)',
            'score': r'(\d+)\s*[-–]\s*(\d+)',
            'time': r'(\d+)m',
            'odds': r'@\s*(\d+[.,]\d+)',
            'stake': r'(?:stake|puntata|€)\s*(\d+(?:[.,]\d+)?)',
            'back': r'\b(back|punta|P\.Exc\.)\b',
            'lay': r'\b(lay|banca|B\.Exc\.)\b',
            'over': r'\b(over|sopra)\s*(\d+[.,]?\d*)',
            'under': r'\b(under|sotto)\s*(\d+[.,]?\d*)',
            'next_goal': r'NEXT\s*GOL|PROSSIMO\s*GOL',
            'cashout': r'\b(COPY\s*CASHOUT|cashout|CASHOUT)\b',
            'cashout_all': r'\b(CASHOUT\s*ALL|CASHOUT\s*TUTTO|CHIUDI\s*TUTTO)\b',
            'ignore_patterns': [r'📈Quota\s*\d+[.,]?\d*', r'📊\d+[.,]?\d+%'],
        }
    
    def set_signal_patterns(self, patterns: Dict):
        """Update signal parsing patterns."""
        self.signal_patterns.update(patterns)
    
    def set_database(self, db):
        """Set database reference for loading custom patterns."""
        self.db = db
        self.reload_custom_patterns()
    
    def reload_custom_patterns(self):
        """Reload custom patterns from database."""
        if hasattr(self, 'db') and self.db:
            try:
                self.custom_patterns = self.db.get_signal_patterns(enabled_only=True)
            except Exception as e:
                print(f"Error loading custom patterns: {e}")
                self.custom_patterns = []
        else:
            self.custom_patterns = []
    
    def set_monitored_chats(self, chat_ids: List[int]):
        """Set list of chat IDs to monitor."""
        self.monitored_chats = chat_ids
    
    def set_callbacks(self, 
                      on_signal: Callable = None, 
                      on_message: Callable = None,
                      on_status: Callable = None):
        """Set callback functions for events."""
        self.signal_callback = on_signal
        self.message_callback = on_message
        self.status_callback = on_status
    
    def parse_signal(self, text: str) -> Optional[Dict]:
        """
        Parse a message text to extract betting signal.
        
        Returns dict with keys: event, side, selection, market_type, odds, stake, raw_text
        or None if no valid signal found.
        """
        signal = {
            'raw_text': text,
            'timestamp': datetime.now().isoformat(),
            'event': None,
            'league': None,
            'side': None,
            'selection': None,
            'market_type': None,
            'odds': None,
            'stake': None,
            'score_home': None,
            'score_away': None,
            'over_line': None,
            'minute': None,
            'cashout_type': None,
        }
        
        custom_patterns = getattr(self, 'custom_patterns', [])
        for cp in custom_patterns:
            try:
                pattern = cp.get('pattern', '')
                if not pattern or not re.search(pattern, text, re.IGNORECASE):
                    continue
                
                event_match = re.search(self.signal_patterns['event'], text)
                if event_match:
                    signal['event'] = event_match.group(1).strip()
                
                score_match = re.search(self.signal_patterns['score'], text)
                if score_match:
                    signal['score_home'] = int(score_match.group(1))
                    signal['score_away'] = int(score_match.group(2))
                
                time_match = re.search(self.signal_patterns['time'], text)
                if time_match:
                    signal['minute'] = int(time_match.group(1))
                
                odds_match = re.search(self.signal_patterns['odds'], text)
                if odds_match:
                    signal['odds'] = float(odds_match.group(1).replace(',', '.'))
                
                min_minute = cp.get('min_minute')
                max_minute = cp.get('max_minute')
                if min_minute and signal['minute'] is not None and signal['minute'] < min_minute:
                    continue
                if max_minute and signal['minute'] is not None and signal['minute'] > max_minute:
                    continue
                
                min_score = cp.get('min_score')
                max_score = cp.get('max_score')
                total_goals = (signal['score_home'] or 0) + (signal['score_away'] or 0)
                if min_score is not None and total_goals < min_score:
                    continue
                if max_score is not None and total_goals > max_score:
                    continue
                
                if cp.get('live_only') and signal['minute'] is None:
                    continue
                
                signal['market_type'] = cp.get('market_type', 'CUSTOM')
                signal['side'] = cp.get('bet_side', 'BACK')
                
                selection_template = cp.get('selection_template', '')
                if selection_template:
                    selection = selection_template
                    selection = selection.replace('{home_score}', str(signal['score_home'] or 0))
                    selection = selection.replace('{away_score}', str(signal['score_away'] or 0))
                    selection = selection.replace('{minute}', str(signal['minute'] or 0))
                    selection = selection.replace('{total_goals}', str(total_goals))
                    selection = selection.replace('{over_line}', str(total_goals + 0.5))
                    signal['selection'] = selection
                else:
                    signal['selection'] = cp.get('name', 'Custom Pattern')
                
                return signal
            except re.error:
                continue
        
        if re.search(self.signal_patterns['cashout_all'], text, re.IGNORECASE):
            signal['market_type'] = 'CASHOUT'
            signal['cashout_type'] = 'ALL'
            return signal
        
        if re.search(self.signal_patterns['cashout'], text, re.IGNORECASE):
            signal['market_type'] = 'CASHOUT'
            signal['cashout_type'] = 'SINGLE'
            event_match = re.search(self.signal_patterns['event'], text)
            if event_match:
                signal['event'] = event_match.group(1).strip()
            return signal
        
        event_match = re.search(self.signal_patterns['event'], text)
        if event_match:
            signal['event'] = event_match.group(1).strip()
        
        league_match = re.search(self.signal_patterns['league'], text)
        if league_match:
            signal['league'] = league_match.group(1).strip()
        
        score_match = re.search(self.signal_patterns['score'], text)
        if score_match:
            signal['score_home'] = int(score_match.group(1))
            signal['score_away'] = int(score_match.group(2))
            total_goals = signal['score_home'] + signal['score_away']
            signal['over_line'] = total_goals + 0.5
        
        time_match = re.search(self.signal_patterns['time'], text)
        if time_match:
            signal['minute'] = int(time_match.group(1))
        
        if re.search(self.signal_patterns['back'], text, re.IGNORECASE):
            signal['side'] = 'BACK'
        elif re.search(self.signal_patterns['lay'], text, re.IGNORECASE):
            signal['side'] = 'LAY'
        
        if re.search(self.signal_patterns['next_goal'], text, re.IGNORECASE):
            signal['market_type'] = 'NEXT_GOAL'
            if signal['score_home'] is not None and signal['score_away'] is not None:
                signal['selection'] = f"Over {signal['over_line']}"
                signal['side'] = 'BACK'
        
        over_match = re.search(self.signal_patterns['over'], text, re.IGNORECASE)
        if over_match:
            signal['selection'] = f"Over {over_match.group(2)}"
            signal['market_type'] = 'OVER_UNDER'
        
        under_match = re.search(self.signal_patterns['under'], text, re.IGNORECASE)
        if under_match:
            signal['selection'] = f"Under {under_match.group(2)}"
            signal['market_type'] = 'OVER_UNDER'
        
        odds_match = re.search(self.signal_patterns['odds'], text)
        if odds_match:
            odds_str = odds_match.group(1).replace(',', '.')
            signal['odds'] = float(odds_str)
        
        stake_match = re.search(self.signal_patterns['stake'], text.lower())
        if stake_match:
            stake_str = stake_match.group(1).replace(',', '.')
            signal['stake'] = float(stake_str)
        
        if signal['event'] and signal['score_home'] is not None:
            signal['selection'] = f"Over {signal['over_line']}"
            signal['side'] = 'BACK'
            signal['market_type'] = 'OVER_UNDER'
            return signal
        
        if signal['side'] and signal['selection']:
            return signal
        
        return None
    
    async def _connect(self):
        """Connect to Telegram."""
        try:
            if self.session_path:
                self.client = TelegramClient(
                    self.session_path,
                    self.api_id,
                    self.api_hash
                )
            elif self.session_string:
                self.client = TelegramClient(
                    StringSession(self.session_string),
                    self.api_id,
                    self.api_hash
                )
            else:
                session_path = os.path.join(os.environ.get('APPDATA', '.'), 'Pickfair', 'telegram_session')
                self.client = TelegramClient(
                    session_path,
                    self.api_id,
                    self.api_hash
                )
            
            await self.client.connect()
            
            if not await self.client.is_user_authorized():
                if self.status_callback:
                    self.status_callback('AUTH_REQUIRED', 'Autenticazione richiesta')
                return False
            
            if self.status_callback:
                self.status_callback('CONNECTED', 'Connesso a Telegram')
            
            return True
            
        except Exception as e:
            if self.status_callback:
                self.status_callback('ERROR', str(e))
            return False
    
    async def _start_listening(self):
        """Start listening for messages."""
        if not self.client:
            return
        
        @self.client.on(events.NewMessage(chats=self.monitored_chats if self.monitored_chats else None))
        async def handler(event):
            message = event.message
            text = message.text or ''
            
            chat_id = event.chat_id
            sender_id = event.sender_id
            
            if self.message_callback:
                self.message_callback({
                    'chat_id': chat_id,
                    'sender_id': sender_id,
                    'text': text,
                    'timestamp': datetime.now().isoformat()
                })
            
            signal = self.parse_signal(text)
            if signal and self.signal_callback:
                signal['chat_id'] = chat_id
                signal['sender_id'] = sender_id
                self.signal_callback(signal)
        
        self.running = True
        if self.status_callback:
            self.status_callback('LISTENING', f'In ascolto su {len(self.monitored_chats)} chat')
        
        await self.client.run_until_disconnected()
    
    def _run_loop(self):
        """Run the asyncio event loop in a thread."""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        
        try:
            connected = self.loop.run_until_complete(self._connect())
            if connected:
                self.loop.run_until_complete(self._start_listening())
        except Exception as e:
            if self.status_callback:
                self.status_callback('ERROR', str(e))
        finally:
            self.running = False
            if self.loop:
                self.loop.close()
    
    def start(self):
        """Start the listener in a background thread."""
        if self.running:
            return
        
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
    
    def stop(self):
        """Stop the listener."""
        self.running = False
        
        if self.client and self.loop:
            try:
                future = asyncio.run_coroutine_threadsafe(
                    self.client.disconnect(),
                    self.loop
                )
                future.result(timeout=5)
            except:
                pass
        
        if self.status_callback:
            self.status_callback('STOPPED', 'Listener fermato')
    
    def get_session_string(self) -> Optional[str]:
        """Get current session string for saving."""
        if self.client:
            return self.client.session.save()
        return None
    
    async def request_code(self, phone: str):
        """Request authentication code."""
        if not self.client:
            self.client = TelegramClient(
                StringSession(),
                self.api_id,
                self.api_hash
            )
            await self.client.connect()
        
        await self.client.send_code_request(phone)
    
    async def sign_in(self, phone: str, code: str, password: str = None):
        """Complete sign in with code."""
        try:
            await self.client.sign_in(phone, code, password=password)
            return True, self.client.session.save()
        except Exception as e:
            return False, str(e)


class SignalQueue:
    """Thread-safe queue for betting signals."""
    
    def __init__(self, max_size: int = 100):
        self.queue: List[Dict] = []
        self.max_size = max_size
        self.lock = threading.Lock()
    
    def add(self, signal: Dict):
        """Add signal to queue."""
        with self.lock:
            self.queue.append(signal)
            if len(self.queue) > self.max_size:
                self.queue.pop(0)
    
    def get_pending(self) -> List[Dict]:
        """Get all pending signals."""
        with self.lock:
            return list(self.queue)
    
    def remove(self, signal: Dict):
        """Remove a signal from queue."""
        with self.lock:
            if signal in self.queue:
                self.queue.remove(signal)
    
    def clear(self):
        """Clear all signals."""
        with self.lock:
            self.queue.clear()
