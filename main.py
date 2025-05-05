from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
import random

app = FastAPI(title="NutriChat")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize templates
templates = Jinja2Templates(directory="templates")

# Food advice database
food_advice = [
    "Попробуйте приготовить греческий салат с оливковым маслом и фетой - это отличный источник полезных жиров и белка.",
    "На завтрак приготовьте овсянку с ягодами и орехами - это даст вам энергию на весь день.",
    "На обед можно приготовить запеченную куриную грудку с брокколи и киноа.",
    "Для перекуса отлично подойдет горсть миндаля и яблоко.",
    "На ужин приготовьте лосось на пару с овощами - это отличный источник омега-3."
]

# Activity advice database
activity_advice = [
    "Попробуйте начать день с 15-минутной зарядки - это зарядит вас энергией на весь день.",
    "Совершите 30-минутную прогулку в обеденный перерыв - это поможет размять мышцы и улучшить кровообращение.",
    "Вечером можно сделать несколько упражнений на растяжку - это поможет расслабиться после рабочего дня.",
    "Попробуйте йогу - это отлично сочетает физическую активность и релаксацию.",
    "Запишитесь на плавание - это отличная кардио-нагрузка, которая не нагружает суставы."
]

# Supplements advice database
supplements_advice = [
    "Омега-3 жирные кислоты помогают поддерживать здоровье сердца и мозга.",
    "Витамин D особенно важен в зимний период, когда мало солнечного света.",
    "Пробиотики помогают поддерживать здоровую микрофлору кишечника.",
    "Куркума с черным перцем - отличный природный противовоспалительный комплекс.",
    "Спирулина - это суперфуд, богатый белком и микроэлементами."
]

# Random advice database
random_advice = [
    "Пейте достаточное количество воды в течение дня - это важно для всех процессов в организме.",
    "Старайтесь спать 7-8 часов в сутки - это необходимо для восстановления организма.",
    "Практикуйте осознанное питание - ешьте медленно и наслаждайтесь каждым кусочком.",
    "Включайте в рацион разнообразные овощи и фрукты разных цветов.",
    "Планируйте свое питание заранее - это поможет сделать более здоровый выбор."
]

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/advice/{advice_type}")
async def get_advice(advice_type: str):
    if advice_type == "food":
        advice = random.choice(food_advice)
        title = "Совет по питанию"
    elif advice_type == "activity":
        advice = random.choice(activity_advice)
        title = "Совет по активности"
    elif advice_type == "supplements":
        advice = random.choice(supplements_advice)
        title = "Совет по БАДам и суперфудам"
    elif advice_type == "random":
        advice = random.choice(random_advice)
        title = "Рандомный совет"
    else:
        advice = "Неверный тип совета"
        title = "Ошибка"
    
    return {"title": title, "advice": advice}

@app.get("/health")
async def health_check():
    return {"status": "healthy"} 