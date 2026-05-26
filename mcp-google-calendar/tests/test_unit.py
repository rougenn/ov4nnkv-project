"""Unit-тесты для MCP Google Calendar сервера."""

import pytest
from unittest.mock import patch, MagicMock
import os


class TestGetCurrentTimeMoscow:
    """Тесты для get_current_time_moscow."""
    
    def test_returns_success(self):
        """Тест что функция возвращает success=True."""
        with patch.dict(os.environ, {
            'GOOGLE_PROJECT_ID': 'test',
            'GOOGLE_PRIVATE_KEY': 'test',
            'GOOGLE_CLIENT_EMAIL': 'test@test.iam.gserviceaccount.com',
            'GOOGLE_CALENDAR_ID': 'test@group.calendar.google.com',
        }):
            from src.server import get_current_time_moscow
            # FastMCP декоратор оборачивает функцию, вызываем через .fn
            result = get_current_time_moscow.fn()
            
            assert result["success"] is True
            assert "timezone" in result
            assert result["timezone"] == "Europe/Moscow"
            assert "date" in result
            assert "time" in result


class TestCreateCalendarEvent:
    """Тесты для create_calendar_event."""
    
    def test_empty_title_returns_error(self):
        """Тест что пустой title возвращает ошибку."""
        with patch.dict(os.environ, {
            'GOOGLE_PROJECT_ID': 'test',
            'GOOGLE_PRIVATE_KEY': 'test',
            'GOOGLE_CLIENT_EMAIL': 'test@test.iam.gserviceaccount.com',
            'GOOGLE_CALENDAR_ID': 'test@group.calendar.google.com',
        }):
            from src.server import create_calendar_event
            result = create_calendar_event.fn(
                title="",
                start_time="2025-12-11T14:00:00",
                end_time="2025-12-11T15:00:00"
            )
            
            assert result["success"] is False
            assert result["error"]["code"] == "INVALID_PARAMETER"
    
    def test_missing_times_returns_error(self):
        """Тест что отсутствие времени возвращает ошибку."""
        with patch.dict(os.environ, {
            'GOOGLE_PROJECT_ID': 'test',
            'GOOGLE_PRIVATE_KEY': 'test',
            'GOOGLE_CLIENT_EMAIL': 'test@test.iam.gserviceaccount.com',
            'GOOGLE_CALENDAR_ID': 'test@group.calendar.google.com',
        }):
            from src.server import create_calendar_event
            result = create_calendar_event.fn(
                title="Test",
                start_time="",
                end_time=""
            )
            
            assert result["success"] is False
            assert result["error"]["code"] == "INVALID_PARAMETER"


class TestGetEventsForDate:
    """Тесты для get_events_for_date."""
    
    def test_invalid_date_format(self):
        """Тест что неверный формат даты возвращает ошибку."""
        with patch.dict(os.environ, {
            'GOOGLE_PROJECT_ID': 'test',
            'GOOGLE_PRIVATE_KEY': 'test',
            'GOOGLE_CLIENT_EMAIL': 'test@test.iam.gserviceaccount.com',
            'GOOGLE_CALENDAR_ID': 'test@group.calendar.google.com',
        }):
            from src.server import get_events_for_date
            result = get_events_for_date.fn(date="invalid-date")
            
            assert result["success"] is False
            assert result["error"]["code"] == "INVALID_DATE"
