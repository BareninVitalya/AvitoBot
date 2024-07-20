import asyncio
import aiosqlite
from Classes import User, Monitoring, Subscription, Duration, Frequency
db_lock = asyncio.Lock()

async def add_user(user: User):
    async with aiosqlite.connect("bot_database.db") as db:
        await db.execute("""
            INSERT INTO Users (user_id, user_name)
            VALUES (?, ?)
        """, (user.user_id, user.user_name))
        await db.commit()


async def add_subscription(start_date, end_date, frequency: Frequency, duration: Duration, user_id):
    async with db_lock:
        async with aiosqlite.connect("bot_database.db") as db:
            cursor = await db.cursor()
            await cursor.execute("""
                INSERT INTO Subscriptions (start_date, end_date, frequency_id, duration_id)
                VALUES (?, ?, ?, ?)
            """, (start_date, end_date, frequency.frequency_id, duration.duration_id))
            # cursor = await db.execute("SELECT last_insert_rowid()")
            # subscription_id = (await cursor.fetchone())[0]
            last_row_id = cursor.lastrowid
            await db.commit()
    await add_subscription_of_user(user_id, last_row_id)


async def add_subscription_of_user(user_id: int, subscriptions_id: int):
    async with db_lock:
        async with aiosqlite.connect("bot_database.db") as db:
            cursor = await db.cursor()
            await cursor.execute("""
                INSERT INTO Subscriptions_of_users (user_id, subscriptions_id) VALUES (?, ?)
            """, (user_id, subscriptions_id))
            await db.commit()


async def add_monitoring(user: User, frequency: Frequency, city: str, product_name: str, url: str, last_check: str,
                         min_price: int, max_price: int):
    async with aiosqlite.connect("bot_database.db") as db:
        cursor = await db.execute("""
            INSERT INTO Monitorings (user_id, frequency_id, city, product_name, url, last_check, min_price, max_price)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (user.user_id, frequency.frequency_id, city, product_name, url, last_check, min_price, max_price))
        await db.commit()
        last_row_id = cursor.lastrowid
    return last_row_id

# Получить пользователя
async def get_user(user_id: int):
    async with aiosqlite.connect("bot_database.db") as db:
        cursor = await db.execute("""
            SELECT * FROM Users WHERE user_id = ?
        """, (user_id,))
        await db.commit()
        user_data = await cursor.fetchone()
        if user_data is not None:
            return User(user_data[0], user_data[1], await get_subscription_by_user_id(user_id),
                        await get_user_monitorings(user_id), user_data[2])
    return None

async def get_user_monitorings(user_id: int):
    async with aiosqlite.connect("bot_database.db") as db:
        cursor = await db.execute("""
            SELECT * FROM Monitorings WHERE user_id = ?
        """, (user_id,))
        monitorings_data = await cursor.fetchall()
        if monitorings_data is not None:
                monitorings = []
                for data in monitorings_data:
                    monitoring = Monitoring(data[0], data[1], data[2], data[3], data[4], await get_frequency(data[5]),
                                            data[6], data[7], data[8])
                    monitorings.append(monitoring)
                return monitorings
    return None

async def get_subscription_by_user_id(user_id: int):
    async with aiosqlite.connect("bot_database.db") as db:
        cursor = await db.execute("""
            SELECT s.subscription_id, s.start_date, s.end_date, s.frequency_id, s.duration_id
            FROM Subscriptions s
            INNER JOIN Subscriptions_of_users su ON su.subscriptions_id = s.subscription_id
            WHERE su.user_id = ?
        """, (user_id,))
        subscription = await cursor.fetchone()
        if subscription is not None:
            return Subscription(subscription[0], subscription[1], subscription[2], await get_frequency(subscription[3]),
                                await get_duration(subscription[4]))
    return None

async def get_frequencies():
    async with aiosqlite.connect("bot_database.db") as db:
        cursor = await db.execute("""
            SELECT * FROM Frequencies
        """)
        frequencies_data = await cursor.fetchall()
        if frequencies_data is not None:
            frequencies = []
            for data in frequencies_data:
                frequency = Frequency(data[0], data[1], data[2], data[3])
                frequencies.append(frequency)
            return frequencies
    return None

async def get_frequency(frequency_id: int):
    async with aiosqlite.connect("bot_database.db") as db:
        cursor = await db.execute("""
            SELECT * FROM Frequencies WHERE frequency_id = ?
        """, (frequency_id,))
        data = await cursor.fetchone()
        if data is not None:
            return Frequency(data[0], data[1], data[2], data[3])
    return None

async def get_durations():
    async with aiosqlite.connect("bot_database.db") as db:
        cursor = await db.execute("""
            SELECT * FROM Durations
        """)
        durations_data = await cursor.fetchall()
        if durations_data is not None:
            durations = []
            for data in durations_data:
                duration = Duration(data[0], data[1], data[2], data[3])
                durations.append(duration)
            return durations
    return None

async def get_duration(duration_id: int):
    async with aiosqlite.connect("bot_database.db") as db:
        cursor = await db.execute("""
            SELECT * FROM Durations WHERE duration_id = ?
        """, (duration_id,))
        data = await cursor.fetchone()
        if data is not None:
            return Duration(data[0], data[1], data[2], data[3])
    return None

async def get_base_rate():
    async with aiosqlite.connect("bot_database.db") as db:
        cursor = await db.execute("""
            SELECT base_rate FROM Configuration WHERE id = 1
        """)
        base_rate = await cursor.fetchone()
    return base_rate[0] if base_rate else 40

async def get_all_subscriptions():
    async with aiosqlite.connect("bot_database.db") as db:
        cursor = await db.execute("""
            SELECT * FROM Subscriptions
        """)
        subscriptions_data = await cursor.fetchall()
        if subscriptions_data is not None:
            subscriptions = []
            for data in subscriptions_data:
                subscription = Subscription(data[0], data[1], await get_frequency(data[2]),
                                            await get_duration(data[3]))
                subscriptions.append(subscription)
            return subscriptions
    return None

async def get_subscription_by_subscription_id(subscription_id):
    async with aiosqlite.connect("bot_database.db") as db:
        cursor = await db.execute("""
            SELECT * FROM Subscriptions
            WHERE subscription_id = ?
        """, (subscription_id,))
        data = await cursor.fetchone()
        if data is not None:
            return Subscription(data[0], data[1], await get_frequency(data[2]), await get_duration(data[3]))
    return None


async def update_subscription(subscription: Subscription):
    async with aiosqlite.connect("bot_database.db") as db:
        cursor = await db.cursor()
        await cursor.execute("""
            UPDATE Subscriptions
            SET start_date = ?, end_date = ?, frequency_id = ?, duration_id = ?
            WHERE subscription_id = ?
        """, (subscription.start_date, subscription.end_date, subscription.frequency.frequency_id,
              subscription.duration.duration_id, subscription.subscription_id))
        await db.commit()

async def delete_subscription(subscription_id):
    async with aiosqlite.connect("bot_database.db") as db:
        cursor = await db.cursor()
        await cursor.execute("""
            DELETE FROM Subscriptions
            WHERE subscription_id = ?
        """, (subscription_id,))
        await cursor.execute("""
            DELETE FROM Subscriptions_of_users
            WHERE subscriptions_id = ?
        """, (subscription_id,))
        await db.commit()