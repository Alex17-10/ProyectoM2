"""
FleetLogix - Pipeline ETL Automático
Extrae de PostgreSQL, Transforma y Carga en Snowflake
Ejecución diaria automatizada
"""

from os import times

import psycopg2
import snowflake.connector
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging
import schedule
import time
import json
from typing import Dict, List, Tuple

# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('etl_pipeline.log'),
        logging.StreamHandler()
    ]
)

# Configuración de conexiones
POSTGRES_CONFIG = {
    'host': 'localhost',
    'database': 'fleetlogix',
    'user': 'postgres',
    'password': 'Bootcamp',
    'port': 5432
}

SNOWFLAKE_CONFIG = {
    'user': 'ALEXANDER1710',
    'password': 'snr9YxeF8nmwiMz',
    'account': 'NLOLIHS-DHC85239',
    'warehouse': 'FLEETLOGIX_WH',
    'database': 'FLEETLOGIX_DW',
    'schema': 'ANALYTICS'
}

class FleetLogixETL:
    def __init__(self):
        self.pg_conn = None
        self.sf_conn = None
        self.batch_id = int(datetime.now().timestamp())
        self.metrics = {
            'records_extracted': 0,
            'records_transformed': 0,
            'records_loaded': 0,
            'errors': 0
        }
    
    def connect_databases(self):
        """Establecer conexiones con PostgreSQL y Snowflake"""
        try:
            # PostgreSQL
            self.pg_conn = psycopg2.connect(**POSTGRES_CONFIG)
            logging.info(" Conectado a PostgreSQL")
            
            # Snowflake
            self.sf_conn = snowflake.connector.connect(**SNOWFLAKE_CONFIG)
            import sys
            logging.info(sys.executable)
            logging.info(" Conectado a Snowflake")
            
            return True
        except Exception as e:
            logging.error(f" Error en conexión: {e}")
            return False
    
    def extract_daily_data(self) -> pd.DataFrame:
        """Extraer datos del día anterior de PostgreSQL"""
        logging.info(" Iniciando extracción de datos...")
        
        query = """
        SELECT
            d.delivery_id,
            d.trip_id,
            d.tracking_number,
            d.customer_name,
            d.package_weight_kg,
            d.scheduled_datetime,
            d.delivered_datetime,
            d.delivery_status,
            d.recipient_signature,

            t.departure_datetime,
            t.arrival_datetime,
            t.fuel_consumed_liters,

            v.vehicle_id,
            v.license_plate,
            v.vehicle_type,
            v.capacity_kg,
            v.fuel_type,
            v.acquisition_date,
            v.status AS vehicle_status,

            dr.driver_id,
            dr.employee_code,
            dr.first_name,
            dr.last_name,
            dr.license_number,
            dr.license_expiry,
            dr.phone,
            dr.hire_date,
            dr.status AS driver_status,

            r.route_id,
            r.route_code,
            r.origin_city,
            r.destination_city,
            r.distance_km,
            r.estimated_duration_hours,
            r.toll_cost

        FROM deliveries d
        JOIN trips t
            ON d.trip_id = t.trip_id
        JOIN vehicles v
            ON t.vehicle_id = v.vehicle_id
        JOIN drivers dr
            ON t.driver_id = dr.driver_id
        JOIN routes r
            ON t.route_id = r.route_id

        ORDER BY d.scheduled_datetime;
        """
        
        try:
            df = pd.read_sql(query, self.pg_conn)
            self.metrics['records_extracted'] = len(df)
            logging.info(f" Extraídos {len(df)} registros")
            return df
        except Exception as e:
            logging.error(f" Error en extracción: {e}")
            self.metrics['errors'] += 1
            return pd.DataFrame()
    
    def transform_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """Transformar datos para el modelo dimensional"""
        logging.info(" Iniciando transformación de datos...")
        
        try:
            # Calcular métricas
            df['delivery_time_minutes'] = (
               (
                    pd.to_datetime(df['delivered_datetime']) -
                    pd.to_datetime(df['scheduled_datetime'])
                ).dt.total_seconds() / 60
            ).round(2)

            df['delivery_time_minutes'] = df['delivery_time_minutes'].fillna(0)
            df['delay_minutes'] = df['delivery_time_minutes'].clip(lower=0)
            df['is_on_time'] = df['delay_minutes'] <= 30
            
            # Calcular entregas por hora
            df['trip_duration_hours'] = (
                (pd.to_datetime(df['arrival_datetime']) - 
                 pd.to_datetime(df['departure_datetime'])).dt.total_seconds() / 3600
            ).round(2)
            df['trip_duration_hours'] = (
                df['trip_duration_hours']
                .replace(0, np.nan)
                .fillna(1)
            )
            
            # Agrupar entregas por trip para calcular entregas/hora
            deliveries_per_trip = df.groupby('trip_id').size()
            df['deliveries_in_trip'] = df['trip_id'].map(deliveries_per_trip)
            df['deliveries_per_hour'] = (
                df['deliveries_in_trip'] / df['trip_duration_hours']
            ).round(2)
            
            # Eficiencia de combustible
            df['fuel_efficiency_km_per_liter'] = (
                df['distance_km'] / df['fuel_consumed_liters']
            ).round(2)
            
            # Costo estimado por entrega
            df['cost_per_delivery'] = (
                (df['fuel_consumed_liters'] * 5000 + df['toll_cost']) / 
                df['deliveries_in_trip']
            ).round(2)
            
            # Revenue estimado (ejemplo: $20,000 base + $500 por kg)
            df['revenue_per_delivery'] = (20000 + df['package_weight_kg'] * 500).round(2)
            
            # Validaciones de calidad
            # No permitir tiempos negativos
            # No permitir pesos fuera de rango
            df = df[(df['package_weight_kg'] > 0) & (df['package_weight_kg'] < 10000)]
            
            # Manejar cambios históricos (SCD Type 2 para conductor/vehículo)
            df['valid_from'] = pd.to_datetime(df['scheduled_datetime']).dt.date
            df['valid_to'] = pd.to_datetime('9999-12-31')
            df['is_current'] = True
            
            self.metrics['records_transformed'] = len(df)
            logging.info(f" Transformados {len(df)} registros")
            
            return df
            
        except Exception as e:
            logging.error(f" Error en transformación: {e}")
            self.metrics['errors'] += 1
            return pd.DataFrame()
    
    def load_dimensions(self, df: pd.DataFrame):
        """Cargar o actualizar dimensiones en Snowflake"""
        logging.info(" Cargando dimensiones...")
        
        cursor = self.sf_conn.cursor()
        
        try:
            # Cargar dim_customer (nuevos clientes)
            customers = (
                df[['customer_name', 'destination_city']]
                .drop_duplicates()
                .reset_index(drop=True)
            )
            logging.info(f"Clientes únicos: {len(customers)}")
            cursor.execute("""
                CREATE OR REPLACE TEMP TABLE STG_CUSTOMERS(
                customer_name STRING,
                city STRING
            )
            """)

            customer_data = list(
                customers.itertuples(index=False, name=None)
            )
            batch_size = 5000

            for i in range(0, len(customer_data), batch_size):
                batch = customer_data[i:i+batch_size]
                cursor.executemany("""
                    INSERT INTO STG_CUSTOMERS
                    VALUES(%s,%s)
                """, batch)

            logging.info("Clientes enviados a STG_CUSTOMERS")

            cursor.execute("""
            MERGE INTO DIM_CUSTOMER d

            USING (

            SELECT

            ROW_NUMBER() OVER(
            ORDER BY customer_name
            )
            +
            COALESCE(   
            (
            SELECT MAX(customer_key)
            FROM DIM_CUSTOMER
            ),0) customer_key,

            customer_name,

            city

            FROM STG_CUSTOMERS

            ) s

            ON d.customer_name=s.customer_name

            WHEN NOT MATCHED THEN

            INSERT(
                customer_key,
                customer_name,
                customer_type,
                city,
                first_delivery_date,
                total_deliveries,
                customer_category
            )

            VALUES(
                s.customer_key,
                s.customer_name,
                'Individual',
                s.city,
                CURRENT_DATE(),
                0,
                'Regular'
            )
            """)

            logging.info("Clientes cargados")
            vehicles = df.drop_duplicates(subset=['vehicle_id'])
            logging.info(f"Vehículos únicos: {len(vehicles)}")
            cursor.execute("""
                SELECT COALESCE(MAX(vehicle_key),0)
                FROM dim_vehicle
            """)

            next_vehicle_key = cursor.fetchone()[0] + 1
            
            cursor.execute("""
            CREATE OR REPLACE TEMP TABLE STG_VEHICLES(
                vehicle_key INTEGER,
                vehicle_id INTEGER,
                license_plate STRING,
                vehicle_type STRING,
                capacity_kg NUMBER,
                fuel_type STRING,
                acquisition_date DATE,
                status STRING
            )
            """)
            cursor.execute("TRUNCATE TABLE STG_VEHICLES")
            vehicle_data = []
            for _, row in vehicles.iterrows():
                vehicle_data.append((
                    next_vehicle_key,
                    row.vehicle_id,
                    row.license_plate,
                    row.vehicle_type,
                    row.capacity_kg,
                    row.fuel_type,
                    row.acquisition_date,
                    row.vehicle_status
                ))
                next_vehicle_key += 1
            cursor.executemany("""
            INSERT INTO STG_VEHICLES
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            """, vehicle_data)
            logging.info("Vehículos enviados a STG_VEHICLES")
            cursor.execute("""
                MERGE INTO dim_vehicle v
                USING STG_VEHICLES s

                ON v.vehicle_id = s.vehicle_id
                AND v.is_current = TRUE

                WHEN NOT MATCHED THEN

                INSERT (
                    vehicle_key,
                    vehicle_id,
                    license_plate,
                    vehicle_type,
                    capacity_kg,
                    fuel_type,
                    acquisition_date,
                    age_months,
                    status,
                    last_maintenance_date,
                    valid_from,
                    valid_to,
                    is_current
                )

                VALUES (
                    s.vehicle_key,
                    s.vehicle_id,
                    s.license_plate,
                    s.vehicle_type,
                    s.capacity_kg,
                    s.fuel_type,
                    s.acquisition_date,
                    DATEDIFF(month,s.acquisition_date,CURRENT_DATE()),
                    s.status,
                    NULL,
                    CURRENT_DATE(),
                    '9999-12-31',
                    TRUE
                )
            """)
            logging.info("Vehículos cargados")
            cursor.execute("""
                SELECT COALESCE(MAX(driver_key),0)
                FROM dim_driver
            """)

            next_driver_key = cursor.fetchone()[0] + 1
            drivers = df.drop_duplicates(subset=['driver_id'])

            cursor.execute("""
                CREATE OR REPLACE TEMP TABLE STG_DRIVERS(
                    driver_key INTEGER,
                    driver_id INTEGER,
                    employee_code STRING,
                    full_name STRING,
                    license_number STRING,
                    license_expiry DATE,
                    phone STRING,
                    hire_date DATE,
                    status STRING,
                    experience_months INTEGER
                )
                """)
            driver_data = []
            for _, row in drivers.iterrows():
                driver_data.append((
                    next_driver_key,
                    row.driver_id,
                    row.employee_code,
                    row.first_name + " " + row.last_name,
                    row.license_number,
                    row.license_expiry,
                    row.phone,
                    row.hire_date,
                    row.driver_status,
                    int((datetime.now().date()-row.hire_date).days/30)
                ))
                next_driver_key += 1

            cursor.executemany("""
            INSERT INTO STG_DRIVERS
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, driver_data)

            cursor.execute("""
            MERGE INTO dim_driver d

            USING STG_DRIVERS s

            ON d.driver_id=s.driver_id
            AND d.is_current=TRUE

            WHEN NOT MATCHED THEN

            INSERT(
                driver_key,
                driver_id,
                employee_code,
                full_name,
                license_number,
                license_expiry,
                phone,
                hire_date,
                experience_months,
                status,
                performance_category,
                valid_from,
                valid_to,
                is_current
            )

            VALUES(
                s.driver_key,
                s.driver_id,
                s.employee_code,
                s.full_name,
                s.license_number,
                s.license_expiry,
                s.phone,
                s.hire_date,
                s.experience_months,
                s.status,
                'Medio',
                CURRENT_DATE(),
                '9999-12-31',
                TRUE
            )
            """)    

            logging.info(f"Drivers cargados: {len(driver_data)}")
            cursor.execute("""
                SELECT COALESCE(MAX(route_key),0)
                FROM dim_route
            """)
            next_route_key = cursor.fetchone()[0] + 1
            logging.info("=== Cargando ROUTES ===")
            routes = df.drop_duplicates(subset=['route_id'])
            cursor.execute("""
                CREATE OR REPLACE TEMP TABLE STG_ROUTES(
                    route_key INTEGER,
                    route_id INTEGER,
                    route_code STRING,
                    origin_city STRING,
                    destination_city STRING,
                    distance_km FLOAT,
                    estimated_duration_hours FLOAT,
                    toll_cost FLOAT
                )
            """)

            route_data=[]

            for _, row in routes.iterrows():

                route_data.append((
                    next_route_key,
                    row.route_id,
                    row.route_code,
                    row.origin_city,
                    row.destination_city,
                    row.distance_km,
                    row.estimated_duration_hours,
                    row.toll_cost
                ))
                next_route_key+=1

            cursor.executemany("""
            INSERT INTO STG_ROUTES
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s)
            """,route_data)

            cursor.execute("""
            MERGE INTO dim_route r

            USING STG_ROUTES s

            ON r.route_id=s.route_id

            WHEN NOT MATCHED THEN

            INSERT(
                route_key,
                route_id,
                route_code,
                origin_city,
                destination_city,
                distance_km,
                estimated_duration_hours,
                toll_cost,
                difficulty_level,
                route_type
            )

            VALUES(
                s.route_key,
                s.route_id,
                s.route_code,
                s.origin_city,
                s.destination_city,
                s.distance_km,
                s.estimated_duration_hours,
                s.toll_cost,
                'Medio',
                'Interurbana'
            )
            """)

            logging.info(f"Routes cargadas: {len(route_data)}")
            logging.info("=== Cargando DATES ===")

            dates = df['scheduled_datetime'].dt.date.drop_duplicates()

            cursor.execute("""
                CREATE OR REPLACE TEMP TABLE STG_DATES(
                    full_date DATE
                )
            """)

            cursor.execute("TRUNCATE TABLE STG_DATES")

            date_data = []

            for d in dates:
                date_data.append((d,))

            cursor.executemany("""
                INSERT INTO STG_DATES
                VALUES(%s)
            """, date_data)

            cursor.execute("""
            MERGE INTO dim_date dd

            USING STG_DATES s

            ON dd.full_date = s.full_date

            WHEN NOT MATCHED THEN

            INSERT(
                date_key,
                full_date,
                day_of_week,
                day_name,
                day_of_month,
                day_of_year,
                week_of_year,
                month_num,
                month_name,
                quarter,
                year,
                is_weekend,
                is_holiday,
                holiday_name,
                fiscal_quarter,
                fiscal_year
            )

            VALUES(
                TO_NUMBER(TO_VARCHAR(s.full_date,'YYYYMMDD')),
                s.full_date,
                DAYOFWEEK(s.full_date),
                DAYNAME(s.full_date),
                DAY(s.full_date),
                DAYOFYEAR(s.full_date),
                WEEK(s.full_date),
                MONTH(s.full_date),
                MONTHNAME(s.full_date),
                QUARTER(s.full_date),
                YEAR(s.full_date),
                DAYOFWEEK(s.full_date) IN (1,7),
                FALSE,
                NULL,
                QUARTER(s.full_date),
                YEAR(s.full_date)
            )
            """)

            logging.info("=== Cargando TIMES ===")
            times = sorted(df['scheduled_datetime'].dt.hour.unique())
            time_data = []

            for hour in times:
                hour = int(hour)
                time_data.append((
                    int(hour * 100),hour))
                cursor.execute("""
                    MERGE INTO dim_time tt
                    USING(
                        SELECT
                            %s,
                            %s
                    ) s (
                        time_key,
                        hour
                    )

                    ON tt.time_key=s.time_key

                    WHEN NOT MATCHED THEN

                    INSERT(
                        time_key,
                        hour,
                        minute,
                        second,
                        time_of_day,
                        hour_24,
                        hour_12,
                        am_pm,
                        is_business_hour,
                        shift
                    )

                    VALUES(
                        s.time_key,
                        s.hour,
                        0,
                        0,

                        CASE
                            WHEN s.hour<6 THEN 'Madrugada'
                            WHEN s.hour<12 THEN 'Mañana'
                            WHEN s.hour<18 THEN 'Tarde'
                            ELSE 'Noche'
                        END,

                        LPAD(s.hour,2,'0')||':00',

                        TO_CHAR(
                            TO_TIME(LPAD(s.hour,2,'0')||':00'),
                            'HH12:MI AM'
                        ),

                        CASE
                            WHEN s.hour<12 THEN 'AM'
                            ELSE 'PM'
                        END,

                        s.hour BETWEEN 8 AND 17,

                        CASE
                            WHEN s.hour<8 THEN 'Turno 1'
                            WHEN s.hour<16 THEN 'Turno 2'
                            ELSE 'Turno 3'
                        END
                    );
                """,
                (
                    hour*100,
                    hour
                ))
            # Actualizar dimensiones SCD Type 2 si hay cambios
            # (Ejemplo simplificado para dim_driver)
            self.sf_conn.commit()
            logging.info(" Dimensiones actualizadas")
            
        except Exception as e:
            logging.error(f" Error cargando dimensiones: {e}")
            self.sf_conn.rollback()
            self.metrics['errors'] += 1
            raise
    
    def load_facts(self, df: pd.DataFrame):
        """Cargar hechos en Snowflake"""
        logging.info(" Cargando tabla de hechos...")
        
        cursor = self.sf_conn.cursor()
        
        try:
            # Preparar datos para inserción
            vehicle_dict = {}
            cursor.execute("""
            SELECT vehicle_id, vehicle_key
            FROM dim_vehicle
            WHERE is_current = TRUE
            """)

            for vehicle_id, vehicle_key in cursor.fetchall():
                vehicle_dict[vehicle_id] = vehicle_key
            
            driver_dict = {}

            cursor.execute("""
            SELECT driver_id, driver_key
            FROM dim_driver
            WHERE is_current = TRUE
            """)
            for driver_id, driver_key in cursor.fetchall():
                driver_dict[driver_id] = driver_key

            route_dict = {}

            cursor.execute("""
            SELECT route_id, route_key
            FROM dim_route
            """)
            for route_id, route_key in cursor.fetchall():
                route_dict[route_id] = route_key

            customer_dict = {}

            cursor.execute("""
            SELECT customer_name, customer_key
            FROM dim_customer
            """)
            for customer_name, customer_key in cursor.fetchall():
                customer_dict[customer_name] = customer_key
            fact_data = []
            for _, row in df.iterrows():
                # Obtener keys de dimensiones
                date_key = int(pd.to_datetime(row['scheduled_datetime']).strftime('%Y%m%d'))
                scheduled_time_key = pd.to_datetime(row['scheduled_datetime']).hour * 100
                vehicle_key = vehicle_dict.get(row.vehicle_id)
                driver_key = driver_dict.get(row.driver_id)
                route_key = route_dict.get(row.route_id)
                customer_key = customer_dict.get(row.customer_name)
                if None in (
                    vehicle_key,
                    driver_key,
                    route_key,
                    customer_key
                ):
                    continue
                if pd.isna(row['delivered_datetime']):
                    delivered_time_key = None
                else:
                    delivered_time_key = pd.to_datetime(
                        row['delivered_datetime']
                    ).hour * 100
                fact_data.append((
                    date_key,
                    scheduled_time_key,
                    delivered_time_key,
                    vehicle_key,
                    driver_key,
                    route_key,
                    customer_key,
                    row['delivery_id'],
                    row['trip_id'],
                    row['tracking_number'],
                    row['package_weight_kg'],
                    row['distance_km'],
                    row['fuel_consumed_liters'],
                    row['delivery_time_minutes'],
                    row['delay_minutes'],
                    row['deliveries_per_hour'],
                    row['fuel_efficiency_km_per_liter'],
                    row['cost_per_delivery'],
                    row['revenue_per_delivery'],
                    row['is_on_time'],
                    False,  # is_damaged
                    row['recipient_signature'],
                    row['delivery_status'],
                    self.batch_id
                ))
            
            # Insertar en batch
            batch_size = 5000
            for i in range(0, len(fact_data), batch_size):
                batch = fact_data[i:i+batch_size]
                logging.info(
                    f"Lote {(i // batch_size) + 1} de {((len(fact_data) - 1) // batch_size) + 1}"
                )
                cursor.executemany("""
                    INSERT INTO fact_deliveries (
                        date_key,
                        scheduled_time_key,
                        delivered_time_key,
                        vehicle_key,
                        driver_key,
                        route_key,
                        customer_key,
                        delivery_id,
                        trip_id,
                        tracking_number,
                        package_weight_kg,
                        distance_km,
                        fuel_consumed_liters,
                        delivery_time_minutes,
                        delay_minutes,
                        deliveries_per_hour,
                        fuel_efficiency_km_per_liter,
                        cost_per_delivery,
                        revenue_per_delivery,
                        is_on_time,
                        is_damaged,
                        has_signature,
                        delivery_status,
                        etl_batch_id
                    )

                    VALUES(
                        %s,%s,%s,%s,%s,%s,%s,
                        %s,%s,%s,%s,%s,%s,
                        %s,%s,%s,%s,%s,%s,
                        %s,%s,%s,%s,%s
                    )
                """, batch)
                logging.info("Lote terminado")
            
            self.sf_conn.commit()
            self.metrics['records_loaded'] = len(fact_data)
            logging.info(f" Cargados {len(fact_data)} registros en fact_deliveries")
            
        except Exception as e:
            logging.error(f" Error cargando hechos: {e}")
            self.sf_conn.rollback()
            self.metrics['errors'] += 1
    
    def run_etl(self):
        """Ejecutar pipeline ETL completo"""
        start_time = datetime.now()
        logging.info(f" Iniciando ETL - Batch ID: {self.batch_id}")
        
        try:
            # Conectar
            if not self.connect_databases():
                return
            
            # ETL
            df = self.extract_daily_data()
            if not df.empty:
                df_transformed = self.transform_data(df)
                if not df_transformed.empty:
                    self.load_dimensions(df_transformed)
                    self.load_facts(df_transformed)
            
            # Calcular totales para reportes
            self._calculate_daily_totals()
            
            # Cerrar conexiones
            self.close_connections()
            
            # Log final
            duration = (datetime.now() - start_time).total_seconds()
            logging.info(f" ETL completado en {duration:.2f} segundos")
            logging.info(f" Métricas: {json.dumps(self.metrics, indent=2)}")
            
        except Exception as e:
            logging.error(f" Error fatal en ETL: {e}")
            self.metrics['errors'] += 1
            self.close_connections()
    
    def _calculate_daily_totals(self):
        """Pre-calcular totales para reportes rápidos"""
        cursor = self.sf_conn.cursor()
        
        try:
            # Crear tabla de totales si no existe
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_delivery_summary (
                summary_date DATE,
                total_deliveries INT,
                total_revenue DECIMAL(12,2),
                total_fuel DECIMAL(12,2),
                avg_delivery_time DECIMAL(10,2),
                on_time_deliveries INT,
                etl_batch_id INT
            )
            """)
            
            # Insertar totales del día
            cursor.execute("""
            INSERT INTO daily_delivery_summary
            SELECT
                d.full_date,
                COUNT(*) AS total_deliveries,
                SUM(f.revenue_per_delivery) AS total_revenue,
                SUM(f.fuel_consumed_liters) AS total_fuel,
                AVG(f.delivery_time_minutes) AS avg_delivery_time,
                SUM(CASE WHEN f.is_on_time THEN 1 ELSE 0 END) AS on_time_deliveries,
                %s
            FROM fact_deliveries f
            JOIN dim_date d
                ON f.date_key = d.date_key
            WHERE f.etl_batch_id = %s
            GROUP BY d.full_date
            """, (self.batch_id, self.batch_id))
            self.sf_conn.commit()
            logging.info(" Totales diarios calculados")
            
        except Exception as e:
            logging.error(f" Error calculando totales: {e}")
    
    def close_connections(self):
        """Cerrar conexiones a bases de datos"""
        if self.pg_conn:
            self.pg_conn.close()
        if self.sf_conn:
            self.sf_conn.close()
        logging.info(" Conexiones cerradas")

def job():
    """Función para programar con schedule"""
    etl = FleetLogixETL()
    etl.run_etl()

def main():
    """Función principal - Automatización diaria"""
    logging.info(" Pipeline ETL FleetLogix iniciado")
    
    # Programar ejecución diaria a las 2:00 AM
    schedule.every().day.at("02:00").do(job)
    
    logging.info(" ETL programado para ejecutarse diariamente a las 2:00 AM")
    logging.info("Presiona Ctrl+C para detener")
    
    # Ejecutar una vez al inicio (para pruebas)
    job()
    
    # Loop infinito esperando la hora programada
    while True:
        schedule.run_pending()
        time.sleep(60)  # Verificar cada minuto

if __name__ == "__main__":
    main()