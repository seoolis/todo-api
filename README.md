Запуск

uvicorn main:app

Проверка брокера

1) ./nats-server - запуск сервера
2) ./nats sub "tasks.*" - подписка на события
