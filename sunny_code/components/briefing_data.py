"""Mock data for testing briefings without real APIs."""

from datetime import datetime, timedelta
from typing import List, Dict
import random


class MockWeatherData:
    """Mock weather responses."""

    FORECASTS = [
        {
            "temp": 72,
            "condition": "Partly Cloudy",
            "high": 75,
            "low": 62,
            "humidity": 65,
            "wind_speed": 8,
            "uv_index": 6,
            "sunrise": "6:45 AM",
            "sunset": "8:30 PM",
        },
        {
            "temp": 68,
            "condition": "Rainy",
            "high": 70,
            "low": 58,
            "humidity": 85,
            "wind_speed": 12,
            "uv_index": 2,
            "sunrise": "6:45 AM",
            "sunset": "8:30 PM",
        },
        {
            "temp": 78,
            "condition": "Sunny",
            "high": 82,
            "low": 65,
            "humidity": 45,
            "wind_speed": 5,
            "uv_index": 9,
            "sunrise": "6:45 AM",
            "sunset": "8:30 PM",
        },
    ]

    @staticmethod
    def get_forecast() -> Dict:
        return random.choice(MockWeatherData.FORECASTS)


class MockCalendarData:
    """Mock calendar events."""

    EVENTS = [
        {
            "time": "9:00 AM",
            "title": "Physics 101 Lecture",
            "duration": "1 hour",
            "location": "Science Building, Room 201",
            "priority": "high",
        },
        {
            "time": "11:30 AM",
            "title": "Coffee with Sarah",
            "duration": "30 min",
            "location": "The Daily Grind",
            "priority": "low",
        },
        {
            "time": "2:00 PM",
            "title": "Project SUNNY standup",
            "duration": "15 min",
            "location": "Virtual (Zoom)",
            "priority": "high",
        },
        {
            "time": "4:00 PM",
            "title": "Motorsports club meeting",
            "duration": "1 hour",
            "location": "Student Center, Room 305",
            "priority": "medium",
        },
    ]

    TOMORROW_EVENTS = [
        {
            "time": "10:00 AM",
            "title": "Computer Science exam",
            "duration": "2 hours",
            "priority": "critical",
        },
        {
            "time": "1:00 PM",
            "title": "Lunch meeting with advisor",
            "duration": "1 hour",
            "priority": "high",
        },
        {
            "time": "3:30 PM",
            "title": "Library study session",
            "duration": "2 hours",
            "priority": "medium",
        },
    ]

    @staticmethod
    def get_today_events() -> List[Dict]:
        return MockCalendarData.EVENTS

    @staticmethod
    def get_tomorrow_events() -> List[Dict]:
        return MockCalendarData.TOMORROW_EVENTS


class MockEmailData:
    """Mock email summaries."""

    EMAILS = {
        "urgent": [
            {"sender": "Prof. Martinez", "subject": "Physics assignment due today"},
            {"sender": "Mom", "subject": "Call me when you get a chance"},
        ],
        "action_items": [
            {"sender": "Project Lead", "subject": "Review PR for briefing engine"},
            {"sender": "Advisor", "subject": "Schedule spring semester registration"},
            {"sender": "AWS", "subject": "Billing alert: Account approaching limit"},
        ],
        "fyi": [
            {"sender": "Newsletter", "subject": "Weekly tech digest"},
            {"sender": "LinkedIn", "subject": "You have new profile views"},
            {"sender": "GitHub", "subject": "Weekly digest of your activity"},
        ],
    }

    @staticmethod
    def get_summary() -> Dict:
        return {
            "urgent": len(MockEmailData.EMAILS["urgent"]),
            "action_items": len(MockEmailData.EMAILS["action_items"]),
            "fyi": len(MockEmailData.EMAILS["fyi"]),
            "total": sum(len(v) for v in MockEmailData.EMAILS.values()),
        }

    @staticmethod
    def get_details() -> Dict:
        return MockEmailData.EMAILS


class MockTaskData:
    """Mock task lists."""

    TODAY = [
        {"title": "Physics homework", "status": "in_progress", "due": "Today"},
        {"title": "Review briefing code", "status": "pending", "due": "Today"},
        {"title": "Respond to emails", "status": "pending", "due": "Today"},
        {
            "title": "Book flight home for break",
            "status": "pending",
            "due": "Tomorrow",
        },
        {"title": "Gym session", "status": "pending", "due": "Today"},
        {"title": "Finish CS project", "status": "pending", "due": "This week"},
    ]

    COMPLETED = [
        "Completed: Morning run (8 miles)",
        "Completed: Sent briefing design document",
        "Completed: Attended physics lecture",
    ]

    @staticmethod
    def get_today() -> List[Dict]:
        return MockTaskData.TODAY

    @staticmethod
    def get_completed() -> List[str]:
        return MockTaskData.COMPLETED


class MockTrafficData:
    """Mock commute/traffic data."""

    COMMUTES = [
        {"route": "Home → Campus", "normal": "25 min", "current": "28 min", "status": "Light traffic"},
        {"route": "Home → Gym", "normal": "12 min", "current": "12 min", "status": "Clear"},
        {
            "route": "Home → Downtown",
            "normal": "35 min",
            "current": "45 min",
            "status": "Heavy traffic (rush hour)",
        },
    ]

    @staticmethod
    def get_commute() -> Dict:
        return random.choice(MockTrafficData.COMMUTES)


class MockHealthData:
    """Mock health/wellness data."""

    STATS = {
        "sleep_last_night": "7h 45m",
        "sleep_quality": "Good",
        "steps_today": 8234,
        "steps_goal": 10000,
        "water_intake": "6 of 8 glasses",
        "exercise": "45 min run planned",
        "mood": "Energized",
    }

    @staticmethod
    def get_stats() -> Dict:
        return MockHealthData.STATS


class MockNewsData:
    """Mock news headlines."""

    HEADLINES = [
        "New AI breakthrough announced by research team",
        "Climate report shows positive progress on emissions",
        "Tech company launches new sustainability initiative",
        "Student startup wins innovation award",
        "University announces new degree program",
    ]

    @staticmethod
    def get_headlines() -> List[str]:
        return random.sample(MockNewsData.HEADLINES, 3)


class MockMotorsportsData:
    """Mock motorsports updates."""

    UPDATES = [
        {
            "type": "race_result",
            "event": "Formula 1 - Monaco Grand Prix",
            "winner": "Charles Leclerc",
            "status": "Just finished",
        },
        {
            "type": "upcoming_event",
            "event": "MotoGP - Sachsenring",
            "date": "Next weekend",
            "status": "Practice sessions start Friday",
        },
        {
            "type": "driver_news",
            "headline": "New driver contract signed for 2025 season",
            "team": "Red Bull Racing",
        },
    ]

    @staticmethod
    def get_updates() -> List[Dict]:
        return random.sample(MockMotorsportsData.UPDATES, 2)
