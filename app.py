import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackContext, CallbackQueryHandler
import requests
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime
import random
import string

# Environment variables
TOKEN = os.environ.get('TOKEN')
ADMIN_ID = os.environ.get('ADMIN_ID')
CHANNEL_ID = os.environ.get('CHANNEL_ID')
DATABASE_URL = os.environ.get('DATABASE_URL')

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Database setup
Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True)
    join_date = Column(DateTime, default=datetime.utcnow)
    is_verified = Column(Boolean, default=False)

class EmailAccount(Base):
    __tablename__ = 'emails'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer)
    email = Column(String, unique=True)
    password = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

# Initialize database
engine = create_engine(DATABASE_URL)
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)

# Mail.tm API setup
MAIL_API = "https://api.mail.tm"

def generate_random_string(length=10):
    letters = string.ascii_lowercase
    return ''.join(random.choice(letters) for i in range(length))

async def is_member(telegram_id: int, context: CallbackContext) -> bool:
    try:
        member = await context.bot.get_chat_member(chat_id=CHANNEL_ID, user_id=telegram_id)
        return member.status in ['member', 'administrator', 'creator']
    except Exception as e:
        logger.error(f"Error checking membership: {e}")
        return False

async def start(update: Update, context: CallbackContext):
    user = update.effective_user
    session = Session()
    db_user = session.query(User).filter_by(telegram_id=user.id).first()
    
    if not db_user:
        db_user = User(telegram_id=user.id)
        session.add(db_user)
        session.commit()
    
    if await is_member(user.id, context):
        db_user.is_verified = True
        session.commit()
        await show_main_menu(update)
    else:
        keyboard = [[InlineKeyboardButton("Join Channel", url=f"https://t.me/{CHANNEL_ID}")],
                    [InlineKeyboardButton("Verify", callback_data="verify")]]
        await update.message.reply_text(  # Fixed parenthesis here
            "Please join our channel to use this bot!",
            reply_markup=InlineKeyboardMarkup(keyboard)
    
    session.close()

async def verify(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    session = Session()
    db_user = session.query(User).filter_by(telegram_id=user.id).first()
    
    if await is_member(user.id, context):
        db_user.is_verified = True
        session.commit()
        await query.edit_message_text("Verification successful!")
        await show_main_menu(query)
    else:
        await query.edit_message_text("You haven't joined the channel yet!")
    
    session.close()

async def show_main_menu(update: Update):
    keyboard = [
        [InlineKeyboardButton("Generate New Email", callback_data="new_email")],
        [InlineKeyboardButton("Check Inbox", callback_data="check_inbox")],
        [InlineKeyboardButton("Delete Email", callback_data="delete_email")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.message:
        await update.message.reply_text("Main Menu:", reply_markup=reply_markup)
    else:
        await update.edit_message_text("Main Menu:", reply_markup=reply_markup)

async def new_email(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    
    # Generate random email
    domain_response = requests.get(f"{MAIL_API}/domains").json()
    domain = domain_response['hydra:member'][0]['domain']
    address = f"{generate_random_string()}@{domain}"
    password = generate_random_string(16)
    
    # Create account
    response = requests.post(
        f"{MAIL_API}/accounts",
        json={"address": address, "password": password}
    )
    
    if response.status_code == 201:
        session = Session()
        email_account = EmailAccount(user_id=user.id, email=address, password=password)
        session.add(email_account)
        session.commit()
        session.close()
        await query.edit_message_text(f"Your new email: `{address}`", parse_mode='Markdown')
    else:
        await query.edit_message_text("Failed to create email. Please try again.")

async def check_inbox(update: Update, context: CallbackContext):
    # Implement inbox checking logic here
    await update.callback_query.answer()
    await update.callback_query.edit_message_text("Inbox feature coming soon!")

async def delete_email(update: Update, context: CallbackContext):
    # Implement email deletion logic here
    await update.callback_query.answer()
    await update.callback_query.edit_message_text("Delete feature coming soon!")

async def notify_all(update: Update, context: CallbackContext):
    if str(update.effective_user.id) != ADMIN_ID:
        return
    
    message = " ".join(context.args)
    if not message:
        await update.message.reply_text("Usage: /notifyall <message>")
        return
    
    session = Session()
    users = session.query(User).filter_by(is_verified=True).all()
    session.close()
    
    count = 0
    for user in users:
        try:
            await context.bot.send_message(chat_id=user.telegram_id, text=f"📢 Admin Announcement:\n\n{message}")
            count += 1
        except Exception as e:
            logger.error(f"Failed to send to {user.telegram_id}: {e}")
    
    await update.message.reply_text(f"Notification sent to {count} users")

def main():
    # Create Application
    application = Application.builder().token(TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(verify, pattern="^verify$"))
    application.add_handler(CallbackQueryHandler(new_email, pattern="^new_email$"))
    application.add_handler(CallbackQueryHandler(check_inbox, pattern="^check_inbox$"))
    application.add_handler(CallbackQueryHandler(delete_email, pattern="^delete_email$"))
    application.add_handler(CommandHandler("notifyall", notify_all))
    
    # Start the bot
    if os.environ.get('RENDER'):
        PORT = int(os.environ.get('PORT', 10000))
        WEBHOOK_URL = "https://your-app-name.onrender.com/"  # Update with your actual URL
        application.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            webhook_url=WEBHOOK_URL,
            secret_token='RENDER_WEBHOOK_SECRET'
        )
    else:
        application.run_polling()

if __name__ == "__main__":
    main()
