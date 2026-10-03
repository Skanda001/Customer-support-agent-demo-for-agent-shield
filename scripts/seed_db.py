import asyncio
from decimal import Decimal
import random
import sys
from pathlib import Path
import uuid
from faker import Faker
from sqlalchemy import select, func

# Ensure ticket_demo is in pythonpath
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.session import async_session_factory
from db.models import Customer, Order, Payment, Refund


fake = Faker("en_IN")
Faker.seed(42)
random.seed(42)

CUSTOMER_STATUS_CHOICES = ["active", "suspended", "closed"]
CUSTOMER_STATUS_WEIGHTS = [0.90, 0.08, 0.02]

ORDER_STATUS_CHOICES = ["delivered", "shipped", "processing", "cancelled", "returned"]
ORDER_STATUS_WEIGHTS = [0.60, 0.20, 0.15, 0.03, 0.02]

PAYMENT_METHODS = ["credit_card", "upi", "netbanking", "debit_card"]
CARD_BRANDS = [
    ("4111111111111111", "1111", "Visa"),
    ("5105105105105100", "5100", "Mastercard"),
    ("378282246310005", "1005", "Amex"),
    ("6011111111111117", "1117", "Discover"),
]

PRODUCTS = [
    "Wireless Noise-Canceling Headphones",
    "Ergonomic Mechanical Keyboard",
    "Ultra-Wide Gaming Monitor 27-inch",
    "Smart Fitness Watch Series 5",
    "USB-C Multi-Port Docking Station",
    "Stainless Steel Insulated Water Bottle",
    "Leather Laptop Backpack 15.6-inch",
    "Portable External SSD 1TB",
    "Smart Wi-Fi LED Desk Lamp",
    "Compact Air Purifier with HEPA Filter",
]

REFUND_REASONS = [
    "Defective or damaged product received",
    "Product does not match description",
    "Changed mind before dispatch",
    "Late delivery",
    "Ordered wrong model or size",
]


async def seed():
    print("[seed] Connecting to database...")
    async with async_session_factory() as session:
        # Check existing count
        existing_customers = await session.scalar(select(func.count(Customer.id)))
        if existing_customers and existing_customers >= 2000:
            print(f"[seed] Database already seeded ({existing_customers} customers found). Skipping seed.")
            return

        print("[seed] Seeding 2,000 customers...")
        customers = []
        emails_seen = set()
        for i in range(1, 2001):
            first = fake.first_name().lower()
            last = fake.last_name().lower()
            base_email = f"{first}.{last}@example.com"
            email = base_email
            counter = 1
            while email in emails_seen:
                email = f"{first}.{last}{counter}@example.com"
                counter += 1
            emails_seen.add(email)

            status = random.choices(CUSTOMER_STATUS_CHOICES, weights=CUSTOMER_STATUS_WEIGHTS)[0]
            phone = f"+91 {random.randint(70000, 99999)} {random.randint(10000, 99999)}"
            address = f"{fake.building_number()}, {fake.street_name()}, {fake.city()}, {fake.postcode()}"

            c = Customer(
                id=uuid.uuid4(),
                display_id=i,
                name=f"{first.capitalize()} {last.capitalize()}",
                email=email,
                phone=phone,
                address=address,
                account_status=status,
            )
            customers.append(c)

        # Batch insert customers in 500-row chunks
        for i in range(0, len(customers), 500):
            batch = customers[i : i + 500]
            session.add_all(batch)
            await session.commit()
            print(f"  [seed] Inserted {len(batch)} customers ({min(i + 500, len(customers))}/{len(customers)})")

        print("[seed] Seeding 4,000 orders...")
        orders = []
        for i in range(1, 4001):
            customer = random.choice(customers)
            display_id = 100000 + i
            product = random.choice(PRODUCTS)
            price = Decimal(str(random.randint(199, 4999)))
            status = random.choices(ORDER_STATUS_CHOICES, weights=ORDER_STATUS_WEIGHTS)[0]
            is_return = True if status == "returned" else (random.random() < 0.05)

            o = Order(
                id=uuid.uuid4(),
                display_id=display_id,
                customer_id=customer.id,
                product=product,
                price=price,
                status=status,
                is_return_requested=is_return,
            )
            orders.append(o)

        for i in range(0, len(orders), 500):
            batch = orders[i : i + 500]
            session.add_all(batch)
            await session.commit()
            print(f"  [seed] Inserted {len(batch)} orders ({min(i + 500, len(orders))}/{len(orders)})")

        print("[seed] Seeding 1,500 payments...")
        payments = []
        payment_orders = random.sample(orders, 1500)
        for i, order in enumerate(payment_orders, start=1):
            method = random.choice(PAYMENT_METHODS)
            card_last4 = None
            card_brand = None
            if "card" in method:
                _, card_last4, card_brand = random.choice(CARD_BRANDS)

            p = Payment(
                id=uuid.uuid4(),
                display_id=200000 + i,
                customer_id=order.customer_id,
                order_id=order.id,
                amount=order.price,
                method=method,
                card_last4=card_last4,
                card_brand=card_brand,
                status="success",
            )
            payments.append(p)

        for i in range(0, len(payments), 500):
            batch = payments[i : i + 500]
            session.add_all(batch)
            await session.commit()
            print(f"  [seed] Inserted {len(batch)} payments ({min(i + 500, len(payments))}/{len(payments)})")

        print("[seed] Seeding 300 refunds...")
        refunds = []
        # Target returned / cancelled orders first, then others
        eligible_orders = [o for o in orders if o.status in ("returned", "cancelled")]
        if len(eligible_orders) < 300:
            remaining = [o for o in orders if o not in eligible_orders]
            eligible_orders.extend(random.sample(remaining, 300 - len(eligible_orders)))
        refund_orders = random.sample(eligible_orders, 300)

        for i, order in enumerate(refund_orders, start=1):
            r = Refund(
                id=uuid.uuid4(),
                display_id=300000 + i,
                order_id=order.id,
                amount=order.price,
                reason=random.choice(REFUND_REASONS),
                status=random.choice(["pending", "approved", "completed"]),
            )
            refunds.append(r)

        for i in range(0, len(refunds), 500):
            batch = refunds[i : i + 500]
            session.add_all(batch)
            await session.commit()
            print(f"  [seed] Inserted {len(batch)} refunds ({min(i + 500, len(refunds))}/{len(refunds)})")

        print("[seed] Seeding complete! Zero tickets seeded (sender agent will generate them).")


if __name__ == "__main__":
    asyncio.run(seed())
