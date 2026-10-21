> 🌐 **Note:** The Spanish version of this README is available as a PDF. Some content (charts, diagrams, screenshots) is easier to follow in the PDF version.
>
> 🌐 **Nota:** La versión en español de este README está disponible en formato PDF. Algunos contenidos (gráficas, diagramas, capturas) se ven más claros en la versión PDF.

---

# FleetLogix: Comprehensive Data Project Documentation

This document brings together, in a single flow, the four parts of the FleetLogix project: synthetic data generation, PostgreSQL query optimization, the AWS architecture, and the construction of the Data Warehouse with its ETL process.

## Contents

1. Project description
2. Synthetic data generation
3. PostgreSQL query optimization
4. AWS architecture
5. Data Warehouse construction and ETL process

---

## 1. Project Description

FleetLogix is a transportation and logistics company that operates a fleet of 200 vehicles performing last-mile deliveries in 5 major cities. The company has been running on legacy systems and spreadsheets, but needs to modernize its data infrastructure to compete in today's market.

The goal is to strengthen this infrastructure: populate all tables with massive synthetic data that respects business relationships, develop queries to solve real operational problems, and design a cloud architecture that enables real-time analysis and data-driven decision making.

As a starting point, a base code for synthetic data generation was provided. It had incomplete functionality and several errors affecting the logic and consistency of the generated information. For this reason, a process of analysis, debugging and development was needed to complete the missing sections, fix the inconsistencies found, and ensure the generated data met the relationships, constraints and volumes required by the project.

### Objectives

- Analyze the existing relational model.
- Understand the relationships between entities.
- Generate more than 505,000 synthetic records.
- Maintain referential integrity.
- Respect business rules.
- Validate the quality of the generated data.
- Implement business analysis queries.

### Technologies Used

- PostgreSQL 15
- Python 3
- Faker
- NumPy
- Psycopg2
- Pandas
- DBeaver

---

## 2. Synthetic Data Generation

### 2.1 Data Model

The system consists of six main tables:

- Vehicles
- Drivers
- Routes
- Trips
- Deliveries
- Maintenance

These entities represent the operation of a company dedicated to transporting and distributing goods between different cities in the country.

> **Figure (see PDF):** entity-relationship diagram (DBeaver) with the tables below.
>
> - `vehicles`: vehicle_id, license_plate, vehicle_type, capacity_kg, fuel_type, acquisition_date, status.
> - `drivers`: driver_id, employee_code, first_name, last_name, license_number, license_expiry, phone, hire_date, status.
> - `routes`: route_id, route_code, origin_city, destination_city, distance_km, estimated_duration_hours, toll_cost.
> - `trips`: trip_id, vehicle_id, driver_id, route_id, departure_datetime, arrival_datetime, fuel_consumed_liters, total_weight_kg, status.
> - `deliveries`: delivery_id, trip_id, tracking_number, customer_name, delivery_address, package_weight_kg, scheduled_datetime, delivered_datetime, delivery_status, recipient_signature.
> - `maintenance`: maintenance_id, vehicle_id, maintenance_date, maintenance_type, description, cost, next_maintenance_date, performed_by.
>
> `trips` relates to `vehicles`, `drivers` and `routes`; `deliveries` relates to `trips`; `maintenance` relates to `vehicles`.

### 2.2 Generation Process

A fully automated Python script was developed to populate the database. Generation respected all relationships between tables, avoided inconsistencies, and simulated behavior close to a real logistics operation.

### 2.3 Generated Records

| Table | Records |
|---|---|
| Vehicles | 200 |
| Drivers | 400 |
| Routes | 50 |
| Trips | 100,000 |
| Deliveries | 400,000 |
| Maintenance | 5,000 |

**Total: 505,650 records**

### 2.4 Implemented Business Rules

The following rules were respected during data generation.

**Vehicles**
- Distribution across large trucks, medium trucks, vans and motorcycles.
- Different capacities depending on vehicle type.
- Realistic acquisition dates.
- Active vehicles and vehicles under maintenance.

**Drivers**

Each driver has:
- A unique employee code.
- A valid license.
- A license type.
- A hire date.
- An active or inactive status.

**Routes**

Routes connect the main cities of Colombia:
- Bogotá
- Medellín
- Cali
- Barranquilla
- Cartagena

Each route contains:
- Approximate distance.
- Estimated time.
- Toll cost.

**Trips**

Each trip:
- Has an existing vehicle.
- Has an existing driver.
- Belongs to a valid route.
- Respects the vehicle's maximum capacity.
- Calculates the transported weight.
- Calculates fuel consumption.
- Records departure and arrival dates.

In addition, statuses were distributed using controlled probabilities to simulate a real operation.

**Deliveries**

Each delivery must belong to a trip. The following are generated:
- Customer
- Address
- Weight
- Scheduled time
- Actual time
- Recipient signature
- Delivery status

The number of deliveries per trip varies between two and six packages.

**Maintenance**

Maintenance records are generated in proportion to each vehicle's usage. To do this, the following were analyzed:
- Number of trips made
- Operating period
- Vehicle type

This avoids assigning unrealistic maintenance to rarely used vehicles.

### 2.5 Data Quality Control

After generating the data, a complete validation stage was run. Checks included:

- Referential integrity.
- Temporal consistency.
- Maximum load capacity.
- Fuel consumption.
- Maintenance costs.
- Statistical distribution of statuses.
- Vehicles without trips.
- Drivers without trips.
- Maintenance before the vehicle's purchase date.
- Trips before the driver's hire date.
- Delivery distribution.
- Fuel distribution.
- Trip duration.

These validations ensured the data was consistent before starting the analysis.

---

## 3. PostgreSQL Query Optimization

### 3.1 Optimization Through Indexes

To improve the performance of the system's most expensive queries, several indexes were implemented on the highest-volume tables and on the columns most frequently used in filters (`WHERE`), joins (`JOIN`) and sorting (`ORDER BY`).

| Index | Table | Purpose |
|---|---|---|
| `idx_trips_composite_joins` | trips | Optimize JOINs between trips, vehicles, drivers and routes for completed-trip queries. |
| `idx_trips_departure` | trips | Improve date-range searches using `departure_datetime`. |
| `idx_deliveries_scheduled_datetime` | deliveries | Optimize queries that filter deliveries by scheduled date. |
| `idx_deliveries_status` | deliveries | Speed up queries that filter by delivery status. |
| `idx_maintenance_vehicle_cost` | maintenance | Optimize lookups of maintenance records associated with each vehicle. |
| `idx_drivers_status_license` | drivers | Improve queries on active drivers and license expiration. |
| `idx_routes_metrics` | routes | Facilitate access to route information used in distance and destination calculations. |
| `idx_vehicles_status` | vehicles | Optimize filters on vehicle status. |

It is important to note that creating an index does not mean PostgreSQL will use it in every query. The database optimizer evaluates different execution strategies and picks the one with the lowest estimated cost.

When the execution plan shows a Sequential Scan (Seq Scan), it is usually for one of these reasons:

- The table has few records, so scanning it fully is cheaper than going through an index.
- The query needs to process a large part of the table, so the index adds little benefit.
- The filter condition uses functions or expressions that prevent direct use of the index.
- The main cost of the query lies in later operations such as JOIN, GROUP BY, ORDER BY or window functions, not in the initial record lookup.

Below is the individual analysis of each query using the `EXPLAIN ANALYZE` results.

### 3.2 Individual Query Analysis

**Query 1: Count vehicles by type**
*Business problem:* Understand the composition of the fleet.
- Execution time: 0.295 ms
- Plan used: Seq Scan + HashAggregate

Although there is an index on vehicle status (`idx_vehicles_status`), this query does not filter by that column and only needs to scan the 200 records in the table to group them by type. Given the small table size, PostgreSQL determines that a sequential scan is the most efficient option.

**Query 2: List drivers with licenses about to expire**
*Business problem:* Prevent legal issues from expired licenses.
- Execution time: 0.344 ms
- Plan used: Seq Scan

The index `idx_drivers_status_license` was created to optimize searches on active drivers and license expiration dates. However, this query only filters by `license_expiry` and not by `status`, a condition needed to take advantage of the partial index. In addition, the table has only 400 records, so PostgreSQL opts for a sequential scan.

**Query 3: Total trips by status**
*Business problem:* Monitor ongoing operations.
- Execution time: 52.154 ms
- Plan used: Seq Scan + HashAggregate

Although there are indexes on the `trips` table, the query must read all 100,000 records to group them by status. Since practically the whole table must be processed, an index offers no significant improvement and PostgreSQL chooses a sequential scan.

**Query 4: Total deliveries by destination city in the last 2 months**
*Business problem:* Identify demand by city for resource planning.
- Execution time: 181.751 ms
- Plan used: Bitmap Index Scan

Here PostgreSQL uses the `idx_trips_departure` index through a Bitmap Index Scan to retrieve only the trips from the last 60 days. It then performs the JOINs with the `deliveries` and `routes` tables. Although indexes also exist on routes and trips, the optimizer determines that the date index provides the greatest reduction in records.

**Query 5: Active drivers with number of completed trips**
*Business problem:* Evaluate workload per driver.
- Execution time: 160.908 ms
- Plan used: Seq Scan

Although the `idx_drivers_status_license` index exists, the `drivers` table is small and the query must scan the entire `trips` table to compute the performance metrics. The main cost is in the aggregations over trips, not in finding drivers, so PostgreSQL does not consider the index necessary.

**Query 6: Average deliveries per driver in the last 6 months**
*Business problem:* Measure individual driver productivity.
- Execution time: 213.548 ms
- Plan used: Bitmap Index Scan

The `idx_trips_departure` index is used to retrieve only trips made during the last six months. This initial reduction lowers the volume of data before running the joins and groupings needed to compute each driver's productivity.

**Query 7: Routes with highest fuel consumption per kilometer**
*Business problem:* Identify inefficient routes for optimization.
- Execution time: 169.996 ms
- Plan used: Parallel Seq Scan

Although the `idx_routes_metrics` index was created, most of the workload is processing the `trips` table, where a large number of records meet the filter conditions. In this scenario PostgreSQL gets better performance by distributing the sequential scan across several processes (Parallel Seq Scan) than by using an index.

**Query 8: Delayed deliveries by day of the week**
*Business problem:* Identify delay patterns to improve planning.
- Execution time: 64.293 ms
- Plan used: Bitmap Index Scan

The query uses the `idx_deliveries_scheduled_datetime` index, retrieving only deliveries from the last 90 days before grouping by day of the week.

**Query 9: Maintenance cost per kilometer traveled**
*Business problem:* Evaluate the cost-benefit of each vehicle type.
- Execution time: 2939.531 ms
- Plan used: Index Scan

This query uses the `idx_maintenance_vehicle_cost` index to efficiently access the maintenance records of each vehicle. Even so, it remains the most expensive query because of the large number of JOINs, aggregations and calculations required, plus the large volume of data processed.

**Query 10: Driver efficiency ranking using Window Functions**
*Business problem:* Identify top performers for incentives.
- Execution time: 230.521 ms
- Plan used: Bitmap Index Scan

The `idx_trips_departure` index is used to limit the analysis to trips from the last three months. Most of the execution time comes afterward, from the window functions used to compute the driver ranking.

**Query 11: Trip trend analysis with LAG and LEAD**
*Business problem:* Project future needs based on trends.
- Execution time: 146.630 ms
- Plan used: Seq Scan

Although the composite index `idx_trips_composite_joins` exists, it is designed mainly to optimize joins between tables, not queries that group only by date. In addition, about 90% of trips have the `completed` status, so PostgreSQL considers it more efficient to scan the entire table than to use a low-selectivity index.

**Query 12: Pivot of deliveries by hour and day of the week**
*Business problem:* Optimize operating hours and staffing.
- Execution time: 266.584 ms
- Plan used: Parallel Seq Scan

Although the `idx_deliveries_scheduled_datetime` index exists, the query applies the function `EXTRACT(HOUR FROM scheduled_datetime)`. By using a function on the indexed column, PostgreSQL cannot directly use the index for that part of the filter and decides on a parallel sequential scan, which is more efficient for this type of processing.

### 3.3 Comparison of Times Without and With Indexes

| Query | Without indexes (ms) | With indexes (ms) | Difference (ms) | Improvement (%) | Observation |
|---|---|---|---|---|---|
| 1 | 0.191 | 0.295 | +0.104 | -54.5% | No change. The table has only 200 records; the optimizer keeps the Seq Scan. |
| 2 | 0.141 | 0.344 | +0.203 | -144.0% | Also a small table; the index gives no benefit. |
| 3 | 35.274 | 52.154 | +16.880 | -47.9% | Aggregate query over the whole table; it must read all records. |
| 4 | 213.325 | 181.751 | -31.574 | 14.8% | The date index reduces the set of trips before the JOIN. |
| 5 | 69.153 | 160.908 | +91.755 | -132.7% | The index does not help because the query still reads the whole Trips table. |
| 6 | 153.992 | 213.548 | +59.556 | -38.7% | The filter uses the index, but the JOIN and GROUP BY cost dominates the time. |
| 7 | 188.014 | 169.996 | -18.018 | 9.6% | Slight improvement thanks to the date index. |
| 8 | 145.466 | 64.293 | -81.173 | 55.8% | Big improvement. Seq Scan replaced by Bitmap Index Scan on `scheduled_datetime`. |
| 9 | 12130.860 | 2939.531 | -9191.329 | 75.8% | Biggest improvement of the project. The index removes millions of comparisons and uses Index Scan + Memoize. |
| 10 | 163.943 | 230.521 | +66.578 | -40.6% | The index filters few records; the main cost remains the aggregation. |
| 11 | 148.604 | 146.630 | -1.974 | 1.3% | Minimal difference; sorting remains the bottleneck. |
| 12 | 262.057 | 266.584 | +4.527 | -1.7% | No significant change. Still uses Parallel Seq Scan. |

The comparison shows that indexes are most effective when a query performs selective searches on columns used in `WHERE`, `JOIN` or `ORDER BY`. When a query needs to process most of the table or run complex aggregations, the optimizer usually prefers a Sequential Scan, since the extra cost of accessing the index outweighs the benefit. For this reason, indexes should be created based on query patterns and not indiscriminately.

---

## 4. AWS Architecture

### 4.1 Introduction

This section describes the design of the AWS architecture implemented for FleetLogix. It explains the services used, the infrastructure setup process, how the Lambda functions work, and the procedure for migrating the PostgreSQL database to Amazon RDS. The goal is to document the system's behavior without having to run it, so the reader can understand how the different components of the proposed solution interact.

### 4.2 Architecture Overview

> **Figure (see PDF):** diagram "FleetLogix – AWS Architecture for Real-Time Analytics" (a serverless, integrated platform for monitoring, analysis and decision making in logistics operations). It is organized into:
> - **Data sources:** on-premise operational PostgreSQL, spreadsheets and CSV files, GPS/telematics, mobile app, external APIs.
> - **Data ingestion:** AWS DMS, AWS Glue Data Catalog, Amazon Kinesis Data Streams.
> - **Storage:** Amazon S3 Data Lake (raw-data, processed-data, curated-data, backups, logs).
> - **Processing:** AWS Glue ETL Jobs, Amazon EMR with Apache Spark, AWS Lambda, Amazon Athena.
> - **Analytics and warehouse:** Amazon Redshift as Data Warehouse, Redshift Spectrum, Amazon QuickSight.
> - **Visualization and users:** dashboards, business users, data analysts, mobile app.
> - **Real-time state:** Amazon DynamoDB (deliveries_status, vehicle_tracking, routes_waypoints, alerts_history).
> - **Operational database:** Amazon RDS for PostgreSQL (fleetlogix-db) with AWS Backup.
> - **Lambda functions:** lambda_verificar_entrega (with API Gateway), lambda_calcular_eta (with EventBridge every 5 minutes), lambda_alerta_desvio (with Kinesis Data Streams), and Amazon SNS for alerts.
> - **Cross-cutting services:** IAM, CloudWatch, SNS, CloudTrail, KMS, and S3 for logs and files.
> - **Benefits:** automatic scalability, high availability and resilience, real-time processing, cost optimization, built-in security, advanced analytics.

The FleetLogix architecture was designed to integrate historical data processing and real-time monitoring in a scalable, secure AWS environment. Its main goal is to centralize information from different sources, transform it through ETL processes, and make it available to business users through dashboards and indicators that support decision making.

The data flow starts at the operational sources, where PostgreSQL stores the transactional information generated by the logistics operation, including vehicles, drivers, routes, trips, deliveries and maintenance. The platform can also receive information from CSV files, spreadsheets, GPS devices installed in vehicles, mobile apps used by drivers, and external APIs providing traffic, weather and map data.

For data ingestion, AWS Database Migration Service (DMS) continuously replicates the information stored in PostgreSQL to the cloud, keeping the data in sync without affecting the performance of the transactional system. In parallel, AWS Glue Data Catalog records the structure and schema of the data, making it easier for the different analytics services to discover and use it. When real-time events are generated, such as GPS location updates or changes in delivery status, Amazon Kinesis receives these streams for immediate processing.

All information is initially stored in Amazon S3, which acts as the solution's Data Lake. Inside this repository, data is organized into zones according to its state: a Raw zone where original data is kept, a Processed zone with previously transformed and validated information, a Curated zone with data optimized for analysis, plus areas for backups and system execution logs.

Data processing is mainly performed by AWS Glue, where the ETL processes run to extract the information, clean it, validate business rules, compute indicators and prepare the data for analysis. When data volume grows considerably, Amazon EMR uses Apache Spark to distribute workloads and process large numbers of records in parallel. For fast queries directly on files stored in S3, Amazon Athena allows SQL queries to run without first loading the data into a database.

Once transformed, the information is loaded into Amazon Redshift, which acts as the organization's Data Warehouse. A dimensional model made up of dimension and fact tables is implemented there, optimized for high-performance analytical queries. Where files stored in the Data Lake need to be queried directly, Redshift Spectrum allows access to the information without duplicating it inside the Data Warehouse.

The consolidated data is consumed by Amazon QuickSight, where interactive dashboards and performance indicators are built for deliveries, fuel consumption, operational efficiency, driver performance, delivery times and other strategic metrics. These dashboards are used by both business users and data analysts to support decisions based on up-to-date information.

In addition to historical processing, the architecture includes a real-time processing component. Information coming from GPS devices and mobile apps is temporarily stored in Amazon DynamoDB, which maintains the current state of deliveries, vehicle locations, route points and the history of alerts generated during operation.

Several AWS Lambda functions act on this information. These functions run automatic processes such as checking the status of a delivery, periodically calculating the estimated time of arrival (ETA), and detecting route deviations by continuously analyzing the information received from Amazon Kinesis. When an important event is identified, the functions generate notifications through Amazon SNS, allowing operations teams to be alerted in time.

The whole platform is backed by cross-cutting services that guarantee security, availability and monitoring. AWS IAM manages authentication and access permissions to the different resources, AWS CloudWatch monitors system performance and records metrics and events, AWS CloudTrail keeps an audit history of every action performed in the infrastructure, AWS KMS protects the information through encryption, and AWS Backup automates backup creation for critical services.

Thanks to this architecture, FleetLogix has a modern, scalable and highly available platform that integrates historical data processing with real-time analysis, making it possible to optimize logistics operations, automate critical processes and provide reliable information for strategic decision making.

### 4.3 Resources Created in `aws_setup.py`

The `aws_setup.py` file automates the creation and configuration of the basic AWS infrastructure needed to support the FleetLogix platform. Its purpose is to prepare the environment where the ETL processes, Lambda functions, and historical and real-time data storage will later run.

**Amazon RDS PostgreSQL**

The script creates a managed PostgreSQL instance using Amazon RDS. The configuration sets a `db.t3.micro` instance (AWS free tier), PostgreSQL version 15.4, 20 GB of storage, automatic backups kept for seven days, and defined maintenance and backup windows.

The purpose of this instance is to host FleetLogix's operational database in the cloud, removing the need to manage its own server and ensuring high availability and recovery from failures.

**Amazon S3**

A bucket named `fleetlogix-data` is then created, used as the project's Data Lake. The following folders are created automatically inside the bucket:

- `raw-data/`
- `processed-data/`
- `backups/`
- `logs/`

In addition, a lifecycle policy is configured that automatically moves data stored in the `raw-data` folder to Glacier after 90 days, significantly reducing storage costs.

**Amazon DynamoDB**

The script creates four NoSQL tables for real-time processing.

- `deliveries_status`: stores the current status of each delivery, showing whether an order is pending, in transit or delivered.
- `vehicle_tracking`: continuously records the GPS location of each vehicle along with the update date and time.
- `routes_waypoints`: stores the GPS points that make up each planned route, information later used to detect deviations.
- `alerts_history`: keeps the complete history of alerts generated by the system during the logistics operation.

**AWS Backup**

After creating the RDS instance, the script generates an initial snapshot and configures a seven-day retention policy for automatic backups. This ensures the information can be recovered in case of system failures.

**AWS IAM**

Finally, a role named `FleetLogixLambdaRole` is created, to be used by all the Lambda functions. The role is assigned the policies needed to access:

- AWS Lambda Basic Execution
- Amazon DynamoDB
- Amazon S3
- Amazon SNS

This way the Lambda functions can query tables, store information and send notifications without explicit credentials.

### 4.4 Functions Implemented in `lambda_functions.py`

The `lambda_functions.py` file contains three Lambda functions designed to automate critical logistics processes using a fully serverless model. Each function responds to a different event and runs specific tasks within the platform.

**Lambda function: Verify Delivery**

The `lambda_verificar_entrega()` function checks whether a delivery has been completed by querying the `deliveries_status` table in Amazon DynamoDB directly.

When the mobile app registers a delivery, it sends an event containing the delivery identifier (`delivery_id`) and, optionally, the tracking number (`tracking_number`).

The function first validates that the identifier was received. If it is missing, it responds immediately with an HTTP 400 code indicating the parameter is required.

It then connects to the `deliveries_status` table and looks up the matching record by the primary key `delivery_id`.

If the record exists, it retrieves the delivery's current status, checks whether that status is `delivered`, and builds a response that includes the delivery identifier, the tracking number, the current status and the recorded delivery date.

When the delivery does not exist in DynamoDB, the function returns an HTTP 404 code indicating the requested resource was not found.

If any exception occurs during the query, the function catches the error and returns an HTTP 500 code along with the corresponding message.

This process lets the mobile app query the up-to-date status of any delivery in real time without accessing the main database directly.

**Lambda function: Calculate ETA**

The `lambda_calcular_eta()` function calculates a vehicle's estimated time of arrival (ETA) using its current location, its destination and its reported speed.

It receives as parameters the vehicle identifier, the current GPS location, the destination coordinates and the average speed.

The remaining distance is calculated using a simplified approximation based on geographic coordinates. The remaining time is then estimated from the vehicle's speed.

Finally, the calculated information is stored in the `vehicle_tracking` table, allowing mobile apps and dashboards to constantly check each vehicle's progress.

**Lambda function: Deviation Alert**

The `lambda_alerta_desvio()` function continuously monitors the GPS location of vehicles.

Each time it receives a new position, it queries DynamoDB for the waypoints of the assigned route. It then calculates the minimum distance between the vehicle's current position and the planned route.

When that distance exceeds the established threshold of five kilometers, the system considers that a route deviation exists. At that point a message with the incident information is generated and sent through Amazon SNS to notify the operations team.

In addition, the alert is recorded in the `alerts_history` table, keeping a complete history of all detected events.

### 4.5 Explanation of the `migrar_datos_postgresql()` Function

The `migrar_datos_postgresql()` function does not perform the database migration directly. Its purpose is to automatically generate a Bash script named `migrate_to_rds.sh`, which contains all the instructions needed to copy the information from local PostgreSQL to Amazon RDS.

The process starts by making a full copy of the local database using the `pg_dump` command, generating a SQL file that contains both the structure and the data of all tables.

A connection is then established to the PostgreSQL instance hosted on Amazon RDS and the target database is created.

Finally, the file generated by `pg_dump` is restored using `psql`, recreating the original structure and importing all the information into the AWS-managed instance.

This procedure allows the operational database to be fully migrated to the cloud without changing the existing structure, supporting continuity of the ETL processes and the analytics environment implemented in FleetLogix.

---

## 5. Data Warehouse Construction and ETL Process

To support analytical processes and enable data-driven decision making, an ETL (Extract, Transform, Load) process was designed and implemented to integrate the operational information stored in PostgreSQL into a Data Warehouse built on Snowflake.

The process automates data extraction, applies transformation and quality rules, and loads the information using a dimensional model optimized for analytical queries.

As a starting point, a base code for the Snowflake Data Warehouse implementation was provided. It had incomplete functionality and several errors affecting data loading, transformation and organization. For this reason, a process of analysis, debugging and development was needed to complete the missing sections, fix the inconsistencies found, and ensure the information was loaded correctly, preserving data integrity and the proper functioning of the analytical model.

### 5.1 ETL Process Architecture

The implemented flow has three main stages.

**Extract**

Information is obtained from the PostgreSQL database from the operational tables:

- Vehicles
- Drivers
- Routes
- Trips
- Deliveries
- Maintenance

**Transform**

During this stage, data cleaning, validation and enrichment processes were carried out. The implemented transformations include:

- calculation of actual delivery time;
- duration of each trip;
- fuel efficiency;
- punctuality indicators;
- cost per delivery;
- generation of date and time dimensions;
- validation of weights and times;
- removal of inconsistent records.

These rules ensure that only valid information is loaded into the Data Warehouse.

**Load**

Finally, the information is loaded into Snowflake through automatic processes using staging tables and `MERGE` operations to keep the dimensions and the fact table up to date.

### 5.2 Dimensional Model

A star schema was designed, made up of one fact table and multiple dimensions.

**Fact table**

`FACT_DELIVERIES` contains the main business metrics, including:

- delivery times;
- transported weight;
- fuel consumption;
- costs;
- compliance indicators.

**Dimension tables**

- `DIM_CUSTOMERS`
- `DIM_VEHICLES`
- `DIM_DRIVERS`
- `DIM_ROUTES`
- `DIM_DATE`
- `DIM_TIME`

Each dimension uses surrogate keys to support historical analysis and improve query performance.

### 5.3 Data Quality During the ETL

Before loading into the Data Warehouse, multiple validations were applied, including:

- removal of negative times;
- validation of package weights;
- date consistency;
- normalization of data types;
- null value control;
- validation of business rules.

This process guaranteed the consistency of the analytical information.

### 5.4 Process Automation

The ETL process was developed entirely in Python and can run automatically. On each run, the following are recorded:

- number of records extracted;
- number of records transformed;
- number of records loaded;
- total execution time;
- errors found during the process.

This facilitates monitoring and traceability of the data load.

### 5.5 Data Warehouse Validation

Once loading finished, the following were verified:

- consistency of surrogate keys;
- correspondence between dimensions and the fact table;
- integrity of relationships;
- consistency of calculated metrics;
- correct operation of the load process.

The tests confirmed that the information stored in the Data Warehouse is consistent with the system's operational data.
