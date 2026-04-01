# UAV Flight Log Analysis Platform — System Interaction Description

## Українською

### Опис взаємодії систем

Система побудована як набір взаємопов’язаних компонентів, де кожен виконує окрему роль у процесі аналізу польотних логів безпілотного апарата.

**Odoo** виступає як основна точка входу для користувача. Саме через нього користувач проходить автентифікацію, завантажує бінарний лог-файл польоту, ініціює обробку та переглядає базову інформацію про місію. Таким чином, Odoo вирішує задачу централізованого доступу до системи та забезпечує зручний інтерфейс керування сценарієм аналізу.

**PostgreSQL** є центральним сховищем даних. У ньому зберігаються облікові записи користувачів, інформація про місії, завантажені лог-файли, результати парсингу телеметрії, обчислені метрики польоту, а також текстові AI-висновки. Це дозволяє всім активним компонентам працювати з єдиним джерелом достовірних даних і не дублювати стан системи в різних місцях.

**RabbitMQ** забезпечує асинхронну взаємодію між компонентами. Після того як користувач запускає аналіз, Odoo не виконує важкі обчислення самостійно, а ставить задачу в чергу. Завдяки цьому веб-інтерфейс не блокується, а система залишається стабільною навіть при обробці великих або складних польотних логів. RabbitMQ фактично розділяє користувацький інтерфейс і фонові процеси.

**AI Service** є окремим сервісом із власною локальною LLM-моделлю. Він отримує задачі через RabbitMQ, аналізує вже підготовлені результати польоту та формує текстовий висновок: наприклад, визначає різкі втрати висоти, перевищення швидкості, нестабільні ділянки маршруту або інші аномалії. Результат роботи AI сервісу зберігається в PostgreSQL і пізніше може бути показаний користувачу разом з основними метриками місії.

**3D Visualization Project** є окремим фронтенд-застосунком, куди користувача перенаправляє Odoo. Цей сервіс отримує з PostgreSQL вже підготовлені координати, траєкторію, швидкості та інші дані польоту і відображає їх у вигляді інтерактивної тривимірної моделі. Таким чином, користувач переходить від “сирого” бінарного логу до наочної просторової картини польоту.

**Prometheus** і **Grafana** відповідають за технічний моніторинг системи. Prometheus збирає метрики з Odoo, RabbitMQ, PostgreSQL, AI Service та 3D Viewer, а Grafana візуалізує ці показники у вигляді дашбордів. Це дає змогу контролювати навантаження, затримки, стан черг, помилки сервісів і загальну стабільність платформи.

У майбутньому важкий парсинг логів можна винести в **окремий Parser Service**. У такому випадку Odoo буде лише ставити задачу в RabbitMQ, а спеціалізований сервіс виконуватиме розбір бінарних логів, витягування GPS та IMU повідомлень, розрахунок метрик і збереження результатів у PostgreSQL. Це ще більше зменшить навантаження на Odoo та спростить масштабування системи.

### Як саме взаємодія компонентів вирішує проблему

Проблема полягає в тому, що польотні лог-файли ArduPilot є складними, нечитабельними для кінцевого користувача та потребують спеціалізованого аналізу. Ручна обробка таких файлів займає багато часу, вимагає технічних знань і не дає швидкого уявлення про причини аварії чи особливості проходження місії.

Запропонована система вирішує цю проблему поетапно.

Спочатку **Odoo** приймає лог-файл і керує всім сценарієм обробки через єдиний інтерфейс. Це прибирає потребу запускати окремі скрипти або вручну працювати з сирими файлами.

Далі **RabbitMQ** дозволяє передати обробку у фоновий режим. Завдяки цьому система не змушує користувача чекати завершення важких обчислень у межах одного HTTP-запиту. Це особливо важливо, якщо лог великий або надалі аналіз ускладниться.

Після цього результати потрапляють у **PostgreSQL**, де вони перетворюються з набору сирих даних на структуровану інформацію: координати, часові ряди, швидкості, прискорення, висота, підсумкові метрики місії. Тобто система переводить телеметрію в форму, придатну для технічного аналізу.

Потім **3D Visualization Project** бере ці дані та відображає їх як інтерактивну просторову траєкторію. Це безпосередньо вирішує головну проблему візуального аналізу: користувач бачить, як саме рухався апарат у просторі, де були різкі зміни траєкторії, піки швидкості або нестандартна поведінка.

Паралельно **AI Service** аналізує збережені результати та формує текстовий висновок. Це вирішує проблему складності інтерпретації даних: замість того щоб вручну шукати аномалії в числах і графіках, користувач отримує автоматично сформований опис ключових подій польоту.

Нарешті, **Prometheus** і **Grafana** забезпечують технічну надійність цього рішення. Вони не аналізують політ напряму, але дозволяють підтримувати систему стабільною, вчасно виявляти перевантаження або збої та гарантувати, що інструмент залишатиметься придатним для практичного використання.

Отже, у взаємодії ці компоненти перетворюють сирий бінарний лог польоту на зрозумілий набір результатів:
**завантаження → асинхронна обробка → збереження → 3D-візуалізація → AI-інтерпретація**.
Саме така послідовність і дозволяє вирішити задачу швидкого, зручного й автоматизованого аналізу польотних даних.

---

## In English

### Description of system interaction

The system is designed as a set of interconnected components, each responsible for a specific part of the UAV flight log analysis process.

**Odoo** acts as the main entry point for the user. Through Odoo, the user authenticates, uploads a binary flight log, starts the analysis process, and views basic mission information. In other words, Odoo solves the problem of centralized access and provides a convenient interface for controlling the overall analysis workflow.

**PostgreSQL** serves as the central data storage. It stores user accounts, mission records, uploaded log files, parsed telemetry, calculated flight metrics, and AI-generated textual conclusions. This allows all active services to work with a single source of truth and prevents fragmentation of system state across different components.

**RabbitMQ** is responsible for asynchronous communication between services. When the user starts analysis, Odoo does not perform heavy processing directly. Instead, it publishes a task into a queue. This approach keeps the web interface responsive and prevents blocking even when large or complex flight logs are being processed. RabbitMQ effectively decouples the user-facing layer from background processing.

**AI Service** is a separate service running its own local LLM model. It receives tasks through RabbitMQ, analyzes already prepared flight data, and generates a textual conclusion about the mission. For example, it can identify sudden altitude loss, excessive speed, unstable flight segments, or other anomalies. The generated result is stored in PostgreSQL and can later be shown to the user together with the core mission metrics.

**3D Visualization Project** is a separate frontend application to which the user is redirected from Odoo. This service reads processed coordinates, trajectory data, speed values, and other flight information from PostgreSQL and renders them as an interactive 3D flight path. As a result, the user moves from raw binary logs to a clear spatial representation of the mission.

**Prometheus** and **Grafana** provide technical monitoring of the platform. Prometheus collects metrics from Odoo, RabbitMQ, PostgreSQL, AI Service, and the 3D Viewer, while Grafana presents these metrics through dashboards. This allows the team to monitor service health, queue load, response times, errors, and the general operational stability of the system.

In the future, heavy binary log processing can be moved into a dedicated **Parser Service**. In that case, Odoo would only submit parsing jobs into RabbitMQ, while the specialized parser would extract GPS and IMU messages, calculate metrics, and save processed results into PostgreSQL. This future step would reduce the load on Odoo even further and improve scalability.

### How the interaction between components solves the problem

The core problem is that ArduPilot flight logs are complex, low-level, and not directly useful for end users. Manual analysis of such files is slow, difficult, and requires specific expertise. It is especially inefficient when the goal is to quickly understand mission performance, detect anomalies, or investigate the possible causes of a crash.

The proposed system solves this problem step by step.

First, **Odoo** receives the uploaded flight log and controls the entire workflow through a single interface. This removes the need to run separate scripts or manually work with raw binary data.

Next, **RabbitMQ** moves processing into the background. This means the platform does not force the user to wait for heavy calculations within a single synchronous request. This is important for scalability and usability, especially when logs become larger or analysis becomes more advanced.

Then, processed results are stored in **PostgreSQL**, where raw telemetry is transformed into structured analytical data: coordinates, time series, speed, acceleration, altitude, and final mission metrics. In other words, the system converts raw sensor output into information that is actually suitable for engineering analysis.

After that, the **3D Visualization Project** uses this processed data to display an interactive spatial trajectory. This directly solves the problem of visual interpretation, because the user can clearly see how the UAV moved in space, where critical turns happened, where speed peaks occurred, and where abnormal behavior may have appeared.

At the same time, the **AI Service** analyzes the processed mission data and generates a textual summary. This solves the problem of interpretation complexity: instead of manually studying numbers and charts, the user receives an automatically generated explanation of the most important flight events and anomalies.

Finally, **Prometheus** and **Grafana** ensure that this platform remains technically stable and observable. They do not analyze the flight itself, but they make sure the system that performs the analysis remains reliable, measurable, and maintainable in real usage.

As a whole, these components transform a raw flight log into a meaningful result chain:
**upload → asynchronous processing → storage → 3D visualization → AI interpretation**.

This interaction model is exactly what allows the system to solve the original problem of fast, convenient, and automated flight log analysis.
