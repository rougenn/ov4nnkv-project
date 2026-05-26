import asyncio
from typing import Dict, Optional
from datetime import datetime


class RequestManager:
    """Manage active requests with cancellation support"""

    def __init__(self):
        self.active_requests: Dict[int, asyncio.Task] = {}
        self.request_timestamps: Dict[int, datetime] = {}

    def add_request(self, user_id: int, task: asyncio.Task):
        """Add a new active request"""
        self.cancel_request(user_id)
        self.active_requests[user_id] = task
        self.request_timestamps[user_id] = datetime.now()

    def cancel_request(self, user_id: int):
        """Cancel active request for user"""
        if user_id in self.active_requests:
            task = self.active_requests[user_id]
            if not task.done():
                task.cancel()
            del self.active_requests[user_id]
        if user_id in self.request_timestamps:
            del self.request_timestamps[user_id]

    def get_active_request(self, user_id: int) -> Optional[asyncio.Task]:
        """Get active request for user"""
        return self.active_requests.get(user_id)

    def cleanup_old_requests(self, max_age_seconds: int = 300):
        """Clean up requests older than specified age"""
        now = datetime.now()
        users_to_remove = []

        for user_id, timestamp in self.request_timestamps.items():
            if (now - timestamp).total_seconds() > max_age_seconds:
                users_to_remove.append(user_id)

        for user_id in users_to_remove:
            self.cancel_request(user_id)


request_manager = RequestManager()
