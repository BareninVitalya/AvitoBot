class User:
    def __init__(self, user_id=None, user_name=None, subscription=None, monitorings=None, max_count_monitor=None):
        self.user_id = user_id
        self.user_name = user_name
        self.subscription = subscription
        self.monitorings = monitorings
        self.max_count_monitor = max_count_monitor

    def __str__(self):
        return f"User(id={self.user_id}, name={self.user_name})"

class Subscription:
    def __init__(self, subscription_id=None, start_date=None, end_date=None, frequency=None, duration=None):
        self.subscription_id = subscription_id
        self.start_date = start_date
        self.end_date = end_date
        self.frequency = frequency
        self.duration = duration

    def is_active(self):
        from datetime import datetime
        date_format = "%Y-%m-%d %H:%M:%S.%f"
        start_date = datetime.strptime(self.start_date, date_format)
        end_date = datetime.strptime(self.end_date, date_format)
        current_date = datetime.now()
        return start_date <= current_date <= end_date

class Monitoring:
    def __init__(self, monitoring_id=None, user_id=None, product_name=None, city=None, url=None, frequency=None,
                 last_check=None, min_price=None, max_price=None):
        self.monitoring_id = monitoring_id
        self.user_id = user_id
        self.product_name = product_name
        self.city = city
        self.url = url
        self.frequency = frequency
        self.last_check = last_check
        self.min_price = min_price
        self.max_price = max_price

class Frequency:
    def __init__(self, frequency_id=None, name=None, value_in_minutes=None, koef=None):
        self.frequency_id = frequency_id
        self.name = name
        self.value_in_minutes = value_in_minutes
        self.koef = koef

class Duration:
    def __init__(self, duration_id=None, name=None, value_in_day=None, koef=None):
        self.duration_id = duration_id
        self.name = name
        self.value_in_day = value_in_day
        self.koef = koef