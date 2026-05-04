## Первоначальная установка

Подключиться по SSH и выполнить 1 команду:
```bash
curl -fsSL https://raw.githubusercontent.com/SnowWoolf/SMART_AGRO_mini/main/install.sh | bash
```

## Обновление

Подключиться по SSH и выполнить 1 команду:
```bash
curl -fsSL https://raw.githubusercontent.com/SnowWoolf/SMART_AGRO_mini/main/update.sh | bash
```

Скрипт сравнивает версию каждого локального файла с версией в репо. 
Если найдены файлы для обновления, скрипт останавливает agrosmart_web и agrosmart_sync;
делает полный бэкап файлов приложения, исключая .git и camera_archive;
заменяет нужные файлы;
запускает сервисы и проверяет systemctl is-active --quiet;
при ошибке копирования или старта сервисов останавливает сервисы, восстанавливает файлы из бэкапа, снова запускает сервисы и подробно пишет ошибку/статусы в консоль.



## Статус служб
```bash
systemctl status agrosmart_web
```
```bash
systemctl status agrosmart_sync
```
