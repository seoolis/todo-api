import asyncio
import json
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor

from fastapi import FastAPI, Request, Response, HTTPException, BackgroundTasks, Depends, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from sqlmodel import SQLModel, Field
from sqlalchemy import Column, Integer, String, Boolean, select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker
from starlette.websockets import WebSocketDisconnect

from nats.aio.client import Client as NATS

nats_client = NATS()


Base = declarative_base()
engine = create_async_engine(
    "sqlite+aiosqlite:///./tasks.db"
)
DBSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=AsyncSession)


# вебсокет

class ConnectionManadger:
    def __init__(self):
        self.active_connection: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connection.append(websocket)

    async def handle(self, data, websocket):
        if data == "spec":
            await websocket.send_text("SPEC OK!")
        elif data == "close":
            await self.disconnect(websocket)
        else:
            await websocket.send_text(data * 10)

    async def disconnect(self, websocket: WebSocket):
        await websocket.close()
        self.active_connection.remove(websocket)

    async def broadcast(self, data: str):
        for ws in self.active_connection:
            await ws.send_text(data)


manager = ConnectionManadger()

class TaskModel(SQLModel, table=True):
    __tablename__ = 'tasks'

    id: int | None = Field(primary_key=True)
    title: str
    description: str
    done: bool = False


# Base.metadata.create_all(bind=engine)


async def get_db():
    db = DBSession()
    try:
        yield db
    finally:
        await db.close()


app = FastAPI(
    title="TODO API",
    version="1.0"
)


@app.on_event("startup")
async def on_startup():
    # nats

    #./nats-server
    #./nats sub test
    # uvicorn main:app

    #./nats sub "tasks.*"

    import nats
    async with engine.begin() as conn:
        await conn.run_sync(
            SQLModel.metadata.create_all
        )

    await nats_client.connect("nats://127.0.0.1:4222")

    import json

    #data = {
    #    "foo": 1,
    #    "name": "test"
    #}

    #await nc.publish("test", b"abc123")
    #await nc.publish("test", json.dumps(data).encode())

    async def handle_nats_message(msg):
        data = msg.data.decode()
        print(f"NATS < {msg.subject}: {data}")

        # при каждой отправке данных брокер дублирует их всем клиентам, подключенным по websocket

        # ./nats pub test "HELLO WORLD!"
        await manager.broadcast(data)

    #await nc.subscribe("test", cb=message_handler)

    #await nc.publish("test", b"Hello!")

    await nats_client.subscribe("tasks.*", cb=handle_nats_message)
    print("NATS connected, subs ready.")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    print(f"Request to {request.url.path} processed in {process_time:.4f} seconds")
    return response


@app.get("/add")
def add_numbers(a: int, b: int):
    return {"result": a + b}


class TaskCreate(BaseModel):
    title: str
    description: str


class TaskUpdate(TaskCreate):
    title: str
    description: str
    done: bool = False


class Task(TaskUpdate):
    id: int


tasks: list[Task] = []
next_id = 1


@app.get("/tasks", response_model=list[TaskModel])
async def get_tasks(
        db: DBSession = Depends(get_db)
):
    stmt = select(TaskModel)
    result = await db.execute(stmt)
    return result.scalars()


@app.get("/tasks/{task_id}", response_model=TaskModel)
async def get_task(task_id: int, db: DBSession = Depends(get_db)):
    task = await db.get(TaskModel, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@app.post("/tasks", response_model=TaskModel, status_code=201)
async def create_task(task: TaskCreate, db: DBSession = Depends(get_db)):
    new_task = TaskModel(
        title=task.title,
        description=task.description,
        done=False
    )

    db.add(new_task)
    await db.commit()
    await db.refresh(new_task)

    # Публикуем событие
    await nats_client.publish(
        "tasks.created",
        new_task.model_dump_json().encode()
    )

    return new_task



@app.put("/tasks/{task_id}", response_model=TaskModel)
async def update_task(task_id: int, updated: TaskUpdate, db: DBSession = Depends(get_db)):
    task = await db.get(TaskModel, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    for k, v in updated.model_dump().items():
        setattr(task, k, v)

    db.add(task)
    await db.commit()
    await db.refresh(task)

    # Событие обновления
    await nats_client.publish(
        "tasks.updated",
        task.model_dump_json().encode()
    )

    return task



@app.delete("/tasks/{task_id}", status_code=204)
async def delete_task(task_id: int, db: DBSession = Depends(get_db)):
    task = await db.get(TaskModel, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    await db.delete(task)
    await db.commit()

    # Публикуем событие удаления
    await nats_client.publish(
        "tasks.deleted",
        json.dumps({"id": task_id}).encode()
    )



# тест асинхронных запросов

# @app.get("/async_task")
# async def async_task():
#     await asyncio.sleep(60)
#     return {"message": "ok"}
#
#
# @app.get("/background_task")
# async def background_task(background_task: BackgroundTasks):
#     def slow_time():
#         import time
#
#         time.sleep(10)
#         print("OK!")
#
#     background_task.add_task(slow_time)
#     return {"message": "task started"}
#
#
# excutor = ThreadPoolExecutor(max_workers=2)
# executor = ProcessPoolExecutor(max_workers=2)
#
#
# def blocking_io_task():
#     import time
#
#     time.sleep(60)
#     return "ok"
#
#
# @app.get("/thread_pool_sleep")
# async def thread_pool_sleep():
#     loop = asyncio.get_running_loop()
#     result = await loop.run_in_executor(excutor, blocking_io_task)
#     return {"message": result}
#
#
# def heavy_func(n: int):
#     result = 0
#     for i in range(n):
#         result += i * i
#     return result
#
#
# @app.get("/cpu_task")
# async def cpu_task(n: int = 10_000_000_000):
#     loop = asyncio.get_running_loop()
#     result = await loop.run_in_executor(excutor, heavy_func, n)
#     return {
#         "message": result
#     }

# парсер

from playwright.async_api import async_playwright


class Product(BaseModel):
    name: str
    price: str
    link: str


class CitilinkParser:
    BASE_URL = 'https://www.citilink.ru'

    async def start(self):
        playwright = await async_playwright().start()
        self.browser = await playwright.chromium.launch(headless=False)
        context = await self.browser.new_context()
        self.page = await context.new_page()

    # SnippetProductHorizontalLayout - для другого режима отображения

    async def load_page(self, url):
        await self.page.goto(url)
        await self.page.wait_for_selector(
            '[data-meta-name="SnippetProductVerticalLayout"]',
            timeout=15_000
        )

    async def parce_products(self) -> list[Product]:
        products = []
        cards = await self.page.query_selector_all(
            '[data-meta-name="SnippetProductVerticalLayout"]',
        )
        print(f"Найдено товаров: {len(cards)}")

        for card in cards:
            name_el = await card.query_selector(
                '[data-meta-name="Snippet__title"]'
            )
            name = await name_el.inner_text()

            link_el = await card.query_selector('a[href*="/product/"]')
            href = await link_el.get_attribute("href")

            link = self.BASE_URL + href

            price_el = await card.query_selector(
                "[data-meta-price]"
            )

            price = await price_el.get_attribute("data-meta-price")

            products.append(
                Product(
                    name=name,
                    link=link,
                    price=price
                )
            )

        return products


@app.get("/parser")
async def parser(background_task: BackgroundTasks):
    citi_parser = CitilinkParser()

    async def func(x):
        await citi_parser.start()
        await citi_parser.load_page(x)
        products = await citi_parser.parce_products()
        print(products)

    async def paginator(url, max_pages):
        for page in range(max_pages):
            new_url = url + f"?p={page + 1}"
            await func(new_url)

    category_url = "https://www.citilink.ru/catalog/smartfony"
    background_task.add_task(paginator, category_url, max_pages=5)
    return {
        "message": "Парсер запущен в фоне"
    }





@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)

    async def tick():
        while True:
            await websocket.send_text('FOO!')
            await asyncio.sleep(10)

    asyncio.create_task(tick())

    try:
        while True:
            data = await websocket.receive_text()
            await manager.handle(data, websocket)

    except WebSocketDisconnect:
        await manager.disconnect(websocket)