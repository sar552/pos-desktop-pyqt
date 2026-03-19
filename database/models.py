import datetime
import os
from peewee import (
    SqliteDatabase, Model, CharField, FloatField,
    BooleanField, DateTimeField, TextField, IntegerField,
    ForeignKeyField
)

# SQLite bazamizni yaratish
db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pos_data.db")
db = SqliteDatabase(db_path, pragmas={
    "journal_mode": "wal", 
    "cache_size": -1000 * 32, # 32MB cache
    "foreign_keys": 1,
    "synchronous": 1
})

class BaseModel(Model):
    class Meta:
        database = db

class ItemGroup(BaseModel):
    name = CharField(unique=True, index=True)
    parent_item_group = CharField(null=True)
    is_group = BooleanField(default=False)
    image = CharField(null=True)

class Item(BaseModel):
    """Mahsulotlar (posawesome strukturasiga moslashtirilgan)"""
    item_code = CharField(unique=True, index=True)
    item_name = CharField()
    item_group = CharField(null=True, index=True)
    description = TextField(null=True)
    barcode = CharField(null=True, index=True)
    uom = CharField(null=True)
    image = CharField(null=True)
    
    # Stock info
    has_batch_no = BooleanField(default=False)
    has_serial_no = BooleanField(default=False)
    is_stock_item = BooleanField(default=True)
    allow_negative_stock = BooleanField(default=False)
    actual_qty = FloatField(default=0.0)
    
    # Pricing & Taxes
    taxes = TextField(null=True) # JSON string of tax templates
    custom_barcode = CharField(null=True)
    
    last_sync = DateTimeField(default=datetime.datetime.now)

class Customer(BaseModel):
    """Mijozlar"""
    name = CharField(unique=True, index=True)
    customer_name = CharField()
    customer_group = CharField(null=True)
    territory = CharField(null=True)
    phone = CharField(null=True)
    email = CharField(null=True)
    tax_id = CharField(null=True)
    last_sync = DateTimeField(default=datetime.datetime.now)

class ItemPrice(BaseModel):
    """Mahsulot narxlari (Pricelist)"""
    name = CharField(unique=True)
    item_code = CharField(index=True)
    price_list = CharField()
    price_list_rate = FloatField(default=0.0)
    currency = CharField(default="UZS")
    last_sync = DateTimeField(default=datetime.datetime.now)

class SalesInvoice(BaseModel):
    """Sotuv cheklari (Asosiy jadval)"""
    offline_id = CharField(unique=True, index=True) # UUID yoki Timestamp-MachineID
    name = CharField(null=True) # Serverdan qaytgan nom (masalan: ACC-SINV-2024-00001)
    
    customer = CharField()
    posting_date = DateTimeField(default=datetime.datetime.now)
    
    # Totals
    total_qty = FloatField(default=0.0)
    total = FloatField(default=0.0) # Net total
    net_total = FloatField(default=0.0)
    total_taxes_and_charges = FloatField(default=0.0)
    discount_amount = FloatField(default=0.0)
    grand_total = FloatField(default=0.0)
    paid_amount = FloatField(default=0.0)
    
    # Meta
    pos_profile = CharField()
    company = CharField()
    status = CharField(default="Draft") # Draft / Synced / Cancelled
    sync_message = TextField(null=True)
    
    created_at = DateTimeField(default=datetime.datetime.now)

class SalesInvoiceItem(BaseModel):
    """Sotuv cheki tarkibidagi mahsulotlar"""
    invoice = ForeignKeyField(SalesInvoice, backref='items', on_delete='CASCADE')
    item_code = CharField()
    item_name = CharField()
    qty = FloatField(default=1.0)
    uom = CharField()
    rate = FloatField(default=0.0)
    amount = FloatField(default=0.0)
    
    # Stock details
    batch_no = CharField(null=True)
    serial_no = TextField(null=True)

class SalesInvoicePayment(BaseModel):
    """To'lov turlari"""
    invoice = ForeignKeyField(SalesInvoice, backref='payments', on_delete='CASCADE')
    mode_of_payment = CharField()
    amount = FloatField(default=0.0)
    account = CharField(null=True)

class PosShift(BaseModel):
    """POS smenalari"""
    opening_entry = CharField(null=True, index=True)
    pos_profile = CharField()
    company = CharField()
    user = CharField()
    opening_amounts = TextField(default="{}")
    status = CharField(default="Open")  # Open / Closed
    opened_at = DateTimeField(default=datetime.datetime.now)
    closed_at = DateTimeField(null=True)

class SchemaVersion(BaseModel):
    """Baza migratsiyalari uchun"""
    version = IntegerField(unique=True)
    applied_at = DateTimeField(default=datetime.datetime.now)
    description = CharField(default="")

ALL_MODELS = [
    ItemGroup, Item, Customer, ItemPrice, 
    SalesInvoice, SalesInvoiceItem, SalesInvoicePayment,
    PosShift, SchemaVersion
]
