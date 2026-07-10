import streamlit as st
import psycopg2
from datetime import date
from datetime import datetime
import pandas as pd
import io
import zipfile
import time

# app_start = time.time()

# if "run_count" not in st.session_state:
#     st.session_state.run_count = 0

# st.session_state.run_count += 1

# st.write(f"Run #{st.session_state.run_count}")



if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if "role" not in st.session_state:
    st.session_state.role = None

if "username" not in st.session_state:
    st.session_state.username = None

if "form_id" not in st.session_state:
    st.session_state.form_id = 0

# --- DATABASE ---
#start = time.time()

#@st.cache_resource
def get_connection():
    return psycopg2.connect(
        host=st.secrets["SUPABASE_HOST"],
        dbname=st.secrets["SUPABASE_DB"],
        user=st.secrets["SUPABASE_USER"],
        password=st.secrets["SUPABASE_PASSWORD"],
        port=st.secrets["SUPABASE_PORT"]
    )
#st.write(f"Connection took {time.time() - start:.3f} seconds")

try:
    conn = get_connection()
    cursor = conn.cursor()

except Exception:
    st.error(
        "⚠️ The database is currently unavailable or waking up.\n\n"
        "If the app has been inactive for a while, Supabase may take "
        "30–60 seconds to resume. Please wait a moment and refresh the page."
    )
    st.stop()
    
@st.cache_data(ttl=30)
def load_records_df():
    cursor = conn.cursor()

    cursor.execute('SELECT * FROM "RECORDS"')
    data = cursor.fetchall()

    columns = [desc[0] for desc in cursor.description]

    df = pd.DataFrame(data, columns=columns)

    df['date_dt'] = pd.to_datetime(
        df['DATE'],
        format='%d-%b-%y',
        errors='coerce'
    )

    if df['date_dt'].isna().any():
        df.loc[df['date_dt'].isna(), 'date_dt'] = pd.to_datetime(
            df.loc[df['date_dt'].isna(), 'DATE'],
            errors='coerce'
        )

    num_cols = ['RP_OUT', 'RP_IN', 'CASH_BAL', 'MANDIRI_BAL']

    for col in num_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

    return df

@st.cache_data(ttl=300)
def load_properties():
    cursor = conn.cursor()
    cursor.execute('SELECT "NAME" FROM "PROPERTIES" ORDER BY "NAME"')
    return [row[0] for row in cursor.fetchall()]


@st.cache_data(ttl=300)
def load_accounts():
    cursor = conn.cursor()
    cursor.execute('SELECT "NAME" FROM "ACCOUNTS" ORDER BY "NAME"')
    return [row[0] for row in cursor.fetchall()]


@st.cache_data(ttl=300)
def load_expenses():
    cursor = conn.cursor()
    cursor.execute('SELECT "NAME" FROM "EXPENSES" ORDER BY "NAME"')
    return [row[0] for row in cursor.fetchall()]


@st.cache_data(ttl=300)
def load_income():
    cursor = conn.cursor()
    cursor.execute('SELECT "NAME" FROM "INCOME" ORDER BY "NAME"')
    return [row[0] for row in cursor.fetchall()]

# --- TABLES ---
# cursor.execute("""
# CREATE TABLE IF NOT EXISTS properties (
#     ID INTEGER PRIMARY KEY,
#      name TEXT UNIQUE)""")

# cursor.execute("""
# CREATE TABLE IF NOT EXISTS accounts (
#     id INTEGER PRIMARY KEY,
#     name TEXT UNIQUE)""")

# cursor.execute("""
# CREATE TABLE IF NOT EXISTS expenses (
#     id INTEGER PRIMARY KEY,
#     name TEXT UNIQUE)""")

# cursor.execute("""
# CREATE TABLE IF NOT EXISTS income (
#     id INTEGER PRIMARY KEY,
#     name TEXT UNIQUE)""")

# cursor.execute("""
# CREATE TABLE IF NOT EXISTS records (
#     ID INTEGER PRIMARY KEY,
#     DATE DATE,
#     CATEGORY TEXT,
#     DESCRIPTION TEXT,
#     UNIT TEXT,
#     RP_OUT NUMERIC,
#     RP_IN NUMERIC,
#     ACCOUNT TEXT,
#     CASH_BAL NUMERIC,
#     MANDIRI_BAL NUMERIC)""")

# cursor.execute("""
# CREATE TABLE IF NOT EXISTS Master (
# 	ID INTEGER PRIMARY KEY,
# 	"DATE"	DATE
# 	"CATEGORY"	TEXT,
# 	"ITEM"	TEXT,
# 	"UNIT"	TEXT,
# 	"COUT"	NUMERIC,
# 	"CIN"	NUMERIC,
# 	"ACCOUNT"	TEXT,
# 	"CASH BAL"	NUMERIC,
# 	"MANDIRI BAL"	NUMERIC)""")

# cursor.execute("""
# CREATE TABLE IF NOT EXISTS users (
#     username TEXT PRIMARY KEY,
#     password TEXT NOT NULL,
#     role TEXT NOT NULL)""")

# conn.commit()

# --- FUNCTIONS ---
def get_last_balance():
    cursor.execute("""
        SELECT
            COALESCE("CASH_BAL",0),
            COALESCE("MANDIRI_BAL",0)
        FROM "RECORDS"
        ORDER BY "ID" DESC
        LIMIT 1
    """)
    
    result = cursor.fetchone()
    return result if result else (0,0)

def insert_record(curdat, category, item, nunit, outflow, inflow, account, new_cash, new_mandiri):
    cursor.execute("""
        INSERT INTO "RECORDS"
        (   "DATE",
            "CATEGORY",
            "DESCRIPTION",
            "UNIT",
            "RP_OUT",
            "RP_IN",
            "ACCOUNT",
            "CASH_BAL",
            "MANDIRI_BAL")
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (curdat, category, item, nunit, outflow, inflow, account, new_cash, new_mandiri))

    conn.commit()

def compute_balances(account, inflow, outflow):
    last_cash, last_mandiri = get_last_balance()

    if account == "CASH":
        if inflow > 0:
            new_cash = last_cash + inflow
        else:
            new_cash = last_cash - outflow

        new_mandiri = last_mandiri
    
        if new_cash < 0:
            raise ValueError("Not enough CASH balance for this expense")
        
    elif account == "MANDIRI":
        if inflow > 0:
            new_mandiri = last_mandiri + inflow
        else:
            new_mandiri = last_mandiri - outflow
        
        new_cash = last_cash

        if new_mandiri < 0:
            raise ValueError("Not enough MANDIRI balance for this expense")
        
    else:
        new_cash, new_mandiri = last_cash, last_mandiri

    return new_cash, new_mandiri

def prepare_transaction(entry_type, amount):
    if entry_type == " 📉 In Flow ":
        return amount, 0
    else:
        return 0, amount

def get_names(table):
    cursor.execute(f'SELECT "NAME" FROM "{table.upper()}"')
    return [row[0] for row in cursor.fetchall()]

def record_form(entry_type):
    col1, col2 = st.columns(2)
    if "form_id" not in st.session_state:
        st.session_state.form_id = 0
    form_disabled = entry_type is None    
    with col1:
        # Create sub-columns inside col1 just for the date section
        date_col, display_col = st.columns([1, 1])
        with date_col:
            #curdat1 = st.date_input("Date", value=date.today(),
            curdat1 = st.date_input("Date", value=None,
            min_value=date(2026, 1, 1),
            max_value=date.today(),
            format="DD-MM-YYYY",
            key=f"date_{st.session_state.form_id}",
            disabled=form_disabled)
        
        with display_col:
            st.write("######")
            if curdat1:
                st.markdown(f"###### **{curdat1.strftime('%d-%b-%y').upper()}**")
                curdat = curdat1.strftime('%d-%b-%y').upper()
            else:
                #st.markdown("###### **NO DATE SELECTED**")
                curdat = None
                curdat1 = None
        
        item = st.text_input("Description",key=f"item_{st.session_state.form_id}",
                             disabled=form_disabled).upper()
        amount = st.number_input("Amount (IDR)", min_value=0, step=100000,
                                 key=f"amount_{st.session_state.form_id}",
                                 disabled=form_disabled)
        if amount > 0:
            # This formats the number with commas and Rp prefix live
            st.caption(f"💰 **Total: Rp {amount:,.0f}**")
        else:
            st.caption("Enter amount to see formatted total")

    with col2:
        if entry_type == " 📉 In Flow ":
            categories = get_names("income")
        else:
            categories = get_names("expenses")

        label = "Income Category" if entry_type == " 📉 In Flow " else "Expense Category"
#        category = st.selectbox(label, categories)
        category = st.selectbox(
            label, 
            options=categories, 
            index=None, 
            placeholder="--- Select a Category ---",
            key=f"cat_selector_{st.session_state.form_id}",
            disabled=form_disabled)
#        unit = st.text_input("UNIT").upper()
        unit = st.selectbox("Villa Unit", get_names("properties"),
            index=None, 
            placeholder="--- Select Villa Unit ---",
            key=f"unit_{st.session_state.form_id}",
            disabled=form_disabled)
        account = st.selectbox("Account", get_names("accounts"),
            index=None, 
            placeholder="--- Select an Account ---",
            key=f"account_{st.session_state.form_id}",
            disabled=form_disabled)

    return curdat, item, amount, category, unit, account

def create_backup_zip():

    tables = [
        "RECORDS",
        "ACCOUNTS",
        "EXPENSES",
        "INCOME",
        "PROPERTIES",
        "USERS"
    ]

    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for table in tables:
            cursor.execute(f'SELECT * FROM "{table}"')
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            df = pd.DataFrame(rows, columns=columns)
            csv_data = df.to_csv(index=False)
            zf.writestr(f"{table}.csv", csv_data)

    zip_buffer.seek(0)
    return zip_buffer, f"canggutopia_bu_{datetime.now():%Y%m%d}.zip"

# --- Show Login Form
if not st.session_state.logged_in:

    st.title("🔐 Login")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")

    if st.button("Login"):

        cursor.execute("""
            SELECT "ROLE"
            FROM "USERS"
            WHERE "USERNAME"=%s
            AND "PASSWORD"=%s
        """, (username, password))

        user = cursor.fetchone()

        if user:
            st.session_state.logged_in = True
            st.session_state.username = username
            st.session_state.role = user[0]
            st.rerun()
        else:
            st.error("Invalid username or password")

    st.stop()
# --- UI ---
# Set page configuration (optional but looks professional)
st.set_page_config(page_title="Canggutopia Villas", layout="wide")

# --- SIDEBAR MENU ---
with st.sidebar:
    st.title("Canggutopia 🌴")
#     menu = st.radio(
#         "Navigation",
# #        ["Home", "Database", "Record Entry", "Reporting M", "Reporting"]
#         ["Record Entry", "Reports", "All Records", "DB Entry"])

    role = st.session_state.role
    if role == "ADMIN":
        menu = st.sidebar.radio(
            "Navigation",
            ["Record Entry", "All Records", "Reports", "DB Entry"])

        if st.button("Prepare Backup"):
            backup_zip, backup_filename = create_backup_zip()

            st.download_button(
                label="📥 Download Full Backup",
                data=backup_zip,
                file_name=backup_filename,
                mime="application/zip"
            )

    elif role == "USER":
        menu = st.sidebar.radio(
            "Navigation",
            ["Record Entry", "All Records"])
    else:
        menu = st.sidebar.radio(
            "Navigation",
            ["All Records", "Reports"])
        
    st.sidebar.divider()

    if st.sidebar.button("Logout"):
        st.session_state.logged_in = False
        st.session_state.username = None
        st.session_state.role = None
        st.rerun()

# --- 1. HOME PAGE ---
if menu == "Home":
    st.title("🏰 Financial Manager")
    st.write("Welcome to the Master Financial Dashboard. Select an option from the sidebar to begin.")

# --- 2. DATABASE VIEW ---
elif menu == "DB Entry":
    st.title("🗄️ DB Entry")
#    st.title("Canggutopia - Inputs DB 🌴")

    st.write (":violet[Note: For any Edits - contact Admin]")
    # Replace with your actual SQL fetch logic
    # st.dataframe(df)
#    st.info("Displaying raw data from 'Master' table...")
    st.divider()
    st.subheader("Properties")
    col1, col2, col3 = st.columns(3)
    with col1:
        new_source = st.text_input("Add New Property")
        new_prop = new_source.upper()

        if st.button("Add Property"):
            if new_prop:
                try:
                    cursor.execute(
                        'INSERT INTO "PROPERTIES" ("NAME") VALUES (%s)',
                        (new_prop,)
                    )
                    conn.commit()
                    load_properties.clear()
                    st.success("Property added!")
                except Exception as e:
                    conn.rollback()
#                    st.error(f"Database error: {e}")
                    st.warning("Property already exists")
    with col2:
        st.write("Existing Properties")
        sources = load_properties()
        for s in sources:
            st.write(f"- {s}")

#    with col2:
#        st.write("Delete Property")
#        cursor.execute("SELECT name FROM properties")
#        source_list = [s[0] for s in cursor.fetchall()]
#        if source_list:
#            selected_source = st.selectbox("Select Property to Delete", source_list)
#            if st.button("Delete Property"):
#                cursor.execute("DELETE FROM perperties WHERE name = ?", (selected_source,))
#                conn.commit()
#                st.success(f"{selected_source} deleted!")
#        else:
#            st.write("No property to delete")
    st.divider()        
    
    st.subheader("Accounts")
    col1, col2, col3 = st.columns(3)
    with col1:
        new_source = st.text_input("Add New Account")
        new_acct = new_source.upper()

        if st.button("Add Account"):
            if new_acct:
                try:
                    cursor.execute(
                        'INSERT INTO "ACCOUNTS" ("NAME") VALUES (%s)',
                        (new_acct,)
                    )
                    conn.commit()
                    load_accounts.clear()
                    st.success("Account added!")
                except:
                    conn.rollback()
                    st.warning("Account already exists")
    with col2:
        st.write("Existing Accounts")
        accounts = load_accounts()
        for s in accounts:
            st.write(f"- {s}")
    st.divider()
    
    st.subheader("Expenses")
    col1, col2, col3 = st.columns(3)
    with col1:
        new_source = st.text_input('Add New Expense - :yellow[Please put leading "EXP - "]')
        new_exp = new_source.upper()

        if st.button("Add Expense"):
            if new_exp:
                try:
                    cursor.execute(
                        'INSERT INTO "EXPENSES" ("NAME") VALUES (%s)',
                        (new_exp,)
                    )
                    conn.commit()
                    load_expenses.clear()
                    st.success("Expense added!")
                except:
                    conn.rollback()
                    st.warning("Expense already exists")
    with col2:
        st.write("Existing Expenses")
        expenses = load_expenses()
        for s in expenses:
            st.write(f"- {s}")
    st.divider()

    st.subheader("Income")
    col1, col2, col3 = st.columns(3)
    with col1:

        new_source = st.text_input('Add New Income - :yellow[Please put leading "INC - "]')
        new_inco = new_source.upper()

        if st.button("Add Income"):
            if new_inco:
                try:
                    cursor.execute(
                        'INSERT INTO "INCOME" ("NAME") VALUES (%s)',
                        (new_inco,)
                    )
                    conn.commit()
                    load_income.clear()
                    st.success("Income added!")
                except Exception as e:
                    conn.rollback()
#                    st.error(f"Database error: {e}")
                    st.warning("Income already exists")
    with col2:
        st.write("Existing Income")
        income = load_income()
        for s in income:
            st.write(f"- {s}")

#    with col3:
#        cursor.execute("SELECT name FROM income")
#        inc = [s[0] for s in cursor.fetchall()]
#        if inc:
#            sel_inc = st.selectbox("Select Entry to Update",inc)
#            new_inc = st.text_input("Update to:")
#            if new_inc:
#                if st.button("Update Entry"):
#                    cursor.execute("UPDATE income SET name = ? WHERE name = ?", (new_inc, sel_inc))
#                    conn.commit()
#                    st.success("Entry updated successfully!")
#                else:
#                    st.write("No entry to update")

elif menu == "All Records":
    st.title("🗄️ Master Records")
    st.divider()

#    st.header("All Master Entries - Records")
    # 1. Fetch data and standardize column names
    df = load_records_df()

    # 2. CREATE FILTER UI
    st.markdown("### 🔍 Filter Records")
    
    # Create two rows of filters
#    row1_col1, row1_col2 = st.columns(2)
    row1_col1, row1_col2, row1_col3 = st.columns(3)

    with row1_col1:
        # Date Range Filter
        min_date = df['date_dt'].min().date() if not df['date_dt'].isna().all() else None
        max_date = df['date_dt'].max().date() if not df['date_dt'].isna().all() else None

        show_all_dates = st.checkbox("Show all dates", value=False)

        if not show_all_dates:
            if max_date:
                    default_start = max_date.replace(day=1)
                    default_end = max_date
            else:
                default_start = None
                default_end = None

            date_range = st.date_input(
                "Select Date Range",
                value=(default_start, default_end) if default_start else [],
                key="db_date_filter"
            )

    with row1_col2:
        if 'ACCOUNT' in df.columns:
            clean_accounts = sorted(df['ACCOUNT'].fillna('').astype(str).unique().tolist())
            display_accounts = [a if a != "" else "N/A" for a in clean_accounts]
            
            selected_account = st.selectbox("Account", ["All"] + display_accounts)
        else:
            st.warning("Column 'ACCOUNT' not found")
            selected_account = "All"

    with row1_col3:
        # Category Filter (Multi-select)
        clean_cats = sorted(df['CATEGORY'].fillna("N/A").astype(str).unique().tolist())
        
        selected_cats = st.multiselect(
            "Category", 
            options=clean_cats,
            default=[], # Starts empty (showing all)
            placeholder="Choose categories..."
        )

        
    # 3. APPLY FILTER LOGIC
    filtered_db = df.copy()

    # Apply Date Range
    if not show_all_dates:
        if len(date_range) == 2:
            start_date, end_date = date_range

            filtered_db = filtered_db[
                (filtered_db['date_dt'].dt.date >= start_date) &
                (filtered_db['date_dt'].dt.date <= end_date)
            ]

    # Apply Category (Multiple)
    if selected_cats:
        # .isin() checks if the row's category exists in the user's selected list
        filtered_db = filtered_db[filtered_db['CATEGORY'].astype(str).fillna("N/A").isin(selected_cats)]

    # Apply Account
    if selected_account != "All":
        filtered_db = filtered_db[filtered_db['ACCOUNT'].astype(str) == selected_account]

    # 4. DISPLAY RESULTS
    st.subheader(f"Results ({len(filtered_db)} records)")
    
    # Dropping the helper date_dt column before showing the table
    display_df = filtered_db.drop(columns=['date_dt'], errors='ignore')
    #st.write(df.dtypes)
    if "ID" in display_df.columns:
        display_df = display_df.sort_values(
            by="ID",
            ascending=False
        )

    st.dataframe(
        display_df, 
#        use_container_width=True, 
        width="stretch",
        hide_index=True,
        column_config={
            "RP_OUT": st.column_config.NumberColumn("RP_OUT", format="%,.0f"),
            "RP_IN": st.column_config.NumberColumn("RP_IN", format="%,.0f"),
            "CASH_BAL": st.column_config.NumberColumn("CASH_BAL", format="%,.0f"),
            "MANDIRI_BAL": st.column_config.NumberColumn("MANDIRI_BAL", format="%,.0f"),
        }
    )
    # --- Show CURRENT BALANCES ---
    st.divider()
    st.subheader("💰 Current Account Balances")

    cursor.execute("""
        SELECT "DATE", "CASH_BAL", "MANDIRI_BAL"
        FROM "RECORDS"
        ORDER BY "ID" DESC
        LIMIT 1
    """)

    latest = cursor.fetchone()

    if latest:
        last_date, cash_bal, mandiri_bal = latest

        balance_df = pd.DataFrame({
            "ACCOUNT": ["CASH", "MANDIRI"],
            "BALANCE": [cash_bal, mandiri_bal]
        })

        st.caption(f"Balances as of: {last_date}")

        st.dataframe(
            balance_df.style.format({"BALANCE": "{:,.0f}"}),
            width="content",
            #use_container_width=False,
            hide_index=True
        )
    else:
        st.warning("No balance data available.")


# --- 3. RECORD ENTRY ---
elif menu == "Record Entry":
    st.title("📝 Record Entry")

    entry_type = st.segmented_control(
        "Transaction Type", 
        [" 📉 In Flow ", " 📈 Out Flow "],
        default=None,
        key=f"entry_type_{st.session_state.form_id}"
    )
    
    if entry_type == " 📉 In Flow ":
        st.subheader("Add :green[Income] Record")
    elif entry_type == " 📈 Out Flow ":
        st.subheader("Add :red[Expense] Record")
    else:
        st.write("**To enable entry fields, please choose :green['In Flow'] to add an :green[Income record] and :red['Out Flow'] to add an :red[Expense record].**")
    st.divider()

    curdat, item, amount, category, unit, account = record_form(entry_type)
    #nitem = item.upper()
#    nunit = unit.upper()
    if unit is None:
        unit = ""

    if st.button("Save Entry"):
        if curdat is None:
            st.error("❌ Error: Please select a date")
        else:

            if item.strip() == "":
                st.error("❌ Please describe the income/expense before saving")
            elif amount < 1:
                st.error("❌ Error: Please review input amount")
            elif category is None:
                st.error("❌ Please select a category before saving")
            #elif unit is None:
            #    st.error("❌ Please select a villa unit before saving")
            elif account is None:
                st.error("❌ Please select an account before saving")
            else:                
                try:
                    inflow, outflow = prepare_transaction(entry_type, amount)

                    new_cash, new_mandiri = compute_balances(account, inflow, outflow)

                    insert_record(
                        curdat,
                        category,
                        item,
                        unit,
                        outflow,
                        inflow,
                        account,
                        new_cash,
                        new_mandiri
                    )
                    load_records_df.clear()
                    st.success("Entry saved!")
                    st.session_state.form_id += 1
                    #if "entry_type" in st.session_state:
                    #    del st.session_state["entry_type"]
                    st.rerun()
                except ValueError as e:
                        conn.rollback()
                        st.error(str(e))
    st.divider()

    # --- SHOW ENRTIES ---
    st.header("Latest 5 Entries")

    # 1. Fetch data and use ORDER BY / LIMIT to get the latest 5
    # We assume 'id' is your primary key; DESC puts the newest at the top

    cursor.execute("""
        SELECT *
        FROM "RECORDS"
        ORDER BY "ID" DESC
        LIMIT 5
    """)
    rows = cursor.fetchall()

    # 2. Get the column names from the cursor description
    # This ensures the labels match your database exactly
    columns = [column[0] for column in cursor.description]

    # 3. Create a DataFrame
    df = pd.DataFrame(rows, columns=columns)

    # 4. Display with formatting (removing decimals for balances/flows)
    st.dataframe(
        df.style.format({
            "RP_OUT": "{:,.0f}",
            "RP_IN": "{:,.0f}",
            "CASH_BAL": "{:,.0f}",
            "MANDIRI_BAL": "{:,.0f}"
        }),
        #use_container_width=True,
        width="stretch",
        hide_index=True  # Optional: hides the 0, 1, 2... row numbers
    )

    st.divider()
    st.subheader("🗑️ Delete from Recent Entries:")

    # 1. Get the allowed IDs from your existing DataFrame
    # This makes sure the user can ONLY pick from the 5 shown in your table
    if not df.empty:
        allowed_ids = df["ID"].tolist() 

        # 2. Setup the UI for deletion
        col1, col2 = st.columns([1, 2])
        
        with col1:
            id_to_delete = st.selectbox("Select ID to Delete", options=allowed_ids)
        
        with col2:
            # A safety checkbox to prevent accidental deletions
            confirm = st.checkbox(f"Confirm: Delete ID #{id_to_delete}?")
        
        # 3. The Delete Action
        if st.button("Delete Permanently", type="primary", disabled=not confirm):
            try:
                # 1. Get the balances of the row immediately BEFORE the one being deleted
                # This is your true "Anchor"
                cursor.execute("""
                    SELECT "CASH_BAL", "MANDIRI_BAL" 
                    FROM "RECORDS" 
                    WHERE "ID" < %s 
                    ORDER BY "ID" DESC LIMIT 1
                """, (id_to_delete,))
                anchor = cursor.fetchone()

                if anchor:
                    running_cash, running_mandiri = anchor
                else:
                    running_cash, running_mandiri = 0, 0

                # 2. Delete the record
                cursor.execute('DELETE FROM "RECORDS" WHERE "ID" = %s', (id_to_delete,))

                # 3. Fetch only the rows that come AFTER the deleted ID
                # These are the ONLY rows whose balances are now incorrect
                cursor.execute("""
                    SELECT "ID", "RP_IN", "RP_OUT", "ACCOUNT" 
                    FROM "RECORDS" 
                    WHERE "ID" > %s 
                    ORDER BY "ID" ASC
                """, (id_to_delete,))
                
                rows_to_fix = cursor.fetchall()

                # 4. Update the subsequent rows
                for row in rows_to_fix:
                    rid, inflow, outflow, acc = row
                    movement = inflow - outflow
                    
                    if "CASH" in acc.upper():
                        running_cash += movement
                    elif "MANDIRI" in acc.upper():
                        running_mandiri += movement
                    
                    cursor.execute("""
                        UPDATE "RECORDS" SET "CASH_BAL" = %s, "MANDIRI_BAL" = %s WHERE "ID" = %s
                    """, (running_cash, running_mandiri, rid))

                conn.commit()
                load_records_df.clear()
                st.success("Record deleted. Balances updated from anchor point.")
                st.rerun()

            except Exception as e:
                conn.rollback()
                st.error(f"Recalculation failed: {e}")
    else:
        st.info("No records found in the latest 5 entries.")

elif menu == "Reports":
    st.title("📊 Financial Performance & Owner Payouts")
    #st.header("📊 Financial Performance & Owner Payouts")
    
    # 1. Fetch data
    cursor.execute('SELECT "DATE", "CATEGORY", "RP_OUT", "RP_IN" FROM "RECORDS"')
    data = cursor.fetchall()
    
    if not data:
        st.warning("No data found in the records table.")
    else:
        df = pd.DataFrame(data, columns=['DATE', 'CATEGORY', 'RP_OUT', 'RP_IN'])

        # --- THE SUPER CLEANER ---
        for col in ['RP_OUT', 'RP_IN']:
            df[col] = df[col].astype(str).str.replace(r'[^\d.]', '', regex=True)
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)

        # 3. CONVERT DATE (DD-MMM-YY)
        df['date_dt'] = pd.to_datetime(df['DATE'], format='%d-%b-%y', errors='coerce')
        df = df.dropna(subset=['date_dt'])

        # 4. FILTER BY YEAR
        df['Year'] = df['date_dt'].dt.year
        year_list = sorted(df['Year'].unique(), reverse=True)
        # Create two columns: a small one for the dropdown, a large one for empty space
        # Adjust the ratio (e.g., 1:3) to fit your taste
        col1, col2 = st.columns([1, 3])  
        with col1:
            selected_year = st.selectbox("Select Year", year_list)
        filtered_df = df[df['Year'] == selected_year].copy()
#        filtered_df['Month'] = filtered_df['date_dt'].dt.strftime('%m - %b')
#        filtered_df['Month'] = filtered_df['date_dt'].dt.strftime('%b')

        month_order = [
            "JANUARY", "FEBRUARY", "MARCH", "APRIL",
            "MAY", "JUNE", "JULY", "AUGUST",
            "SEPTEMBER", "OCTOBER", "NOVEMBER", "DECEMBER"
        ]

        filtered_df['Month'] = filtered_df['date_dt'].dt.strftime('%B').str.upper()

        filtered_df['Month'] = pd.Categorical(
            filtered_df['Month'],
            categories=month_order,
            ordered=True
        )
        st.divider()

        # --- 5. INCOME REPORT (INC) ---
        inc_mask = filtered_df['CATEGORY'].str.strip().str.upper().str.startswith('INC', na=False)
        inc_df = filtered_df[inc_mask].copy()
        
        inc_pivot = pd.DataFrame()
        if not inc_df.empty:
            st.subheader("Operating Revenue")
            inc_pivot = inc_df.pivot_table(index='CATEGORY', columns='Month', values='RP_IN', aggfunc='sum').fillna(0)
            existing_months = [m for m in month_order if m in inc_pivot.columns]
            inc_pivot = inc_pivot[existing_months]
            inc_pivot['Category Total'] = inc_pivot.sum(axis=1)
            inc_pivot.loc['GRAND TOTAL'] = inc_pivot.sum()

            st.dataframe(
                inc_pivot.style.format(lambda x: "{:,.0f}".format(x)), 
                #use_container_width=False)
                width="content")
            
        st.divider()

        # --- 6. EXPENSE REPORT (EXP) EXCLUDING OWNER ---
        exp_mask = filtered_df['CATEGORY'].str.strip().str.upper().str.startswith('EXP', na=False)
        owner_mask = filtered_df['CATEGORY'].str.upper().str.contains('OWNER', na=False)
        exp_df = filtered_df[exp_mask & ~owner_mask].copy()
        
        exp_pivot = pd.DataFrame()
        if not exp_df.empty:
            st.subheader("Operating Expenses")
            exp_pivot = exp_df.pivot_table(index='CATEGORY', columns='Month', values='RP_OUT', aggfunc='sum').fillna(0)
            existing_months = [m for m in month_order if m in exp_pivot.columns]
            exp_pivot = exp_pivot[existing_months]
            exp_pivot['Category Total'] = exp_pivot.sum(axis=1)
            exp_pivot.loc['GRAND TOTAL'] = exp_pivot.sum()
            #st.dataframe(exp_pivot.style.format("{:,.2f}"), use_container_width=True)

            st.dataframe(
                exp_pivot.style.format(lambda x: "{:,.0f}".format(x)), 
                #use_container_width=False)
                width="content")
            
        st.divider()

        # --- 7. PERFORMANCE SUMMARY (Monthly Breakdown) ---
        if not inc_pivot.empty or not exp_pivot.empty:
            # Extract Monthly Grand Totals safely (in case one table is completely empty)
            inc_monthly = inc_pivot.loc['GRAND TOTAL'].drop('Category Total', errors='ignore') if not inc_pivot.empty else pd.Series(dtype=float)
            exp_monthly = exp_pivot.loc['GRAND TOTAL'].drop('Category Total', errors='ignore') if not exp_pivot.empty else pd.Series(dtype=float)
            
            # Monthly Net Profit = Income - Expenses
            monthly_net_profit = inc_monthly.sub(exp_monthly, fill_value=0)

            st.subheader("🏁 Performance Summary")
            
            # Build a new DataFrame where the rows are your metrics and columns are the months
            perf_summary = pd.DataFrame(
                [inc_monthly, exp_monthly, monthly_net_profit], 
                index=["Total Income", "Total Expenses", "Net Profit"]
            ).fillna(0)

            # Add a final 'Yearly Total' column on the far right
            perf_summary['Yearly Total'] = perf_summary.sum(axis=1)

            # Display as a clean interactive dataframe to match your other tables
            st.dataframe(
                perf_summary.style.format("{:,.0f}"), 
                #use_container_width=False
                width="content")

            st.divider()

        # --- 8. OWNER PAYOUT DISTRIBUTION ---
        st.subheader(f"🏠 Owner Payout Distribution ({selected_year})")

        owner_shares = {
            "Villa 1 - Stefan": 0.24,
            "Villa 2 - Basti": 0.252,
            "Villa 3 - Lars": 0.244,
            "Villa 4 - Balint": 0.132,
            "Villa 4 - Frieder": 0.066,
            "Villa 4 - Laura": 0.066
        }

        # Apply shares to the monthly profit
        payout_data = []
        for owner, share in owner_shares.items():
            row = monthly_net_profit * share
            row.name = owner
            payout_data.append(row)

        payout_report = pd.DataFrame(payout_data)
        month_order = [
            "JANUARY", "FEBRUARY", "MARCH", "APRIL",
            "MAY", "JUNE", "JULY", "AUGUST",
            "SEPTEMBER", "OCTOBER", "NOVEMBER", "DECEMBER"
        ]

        existing_months = [m for m in month_order if m in payout_report.columns]

        payout_report = payout_report[existing_months]

        # Add "Yearly Payout" (Horizontal Total)
        payout_report['Yearly Payout'] = payout_report.sum(axis=1)

        # Add "GRAND TOTAL" (Vertical Total)
        payout_report.loc['GRAND TOTAL'] = payout_report.sum()

        # Display using the interactive dataframe style you like
        st.dataframe(
            payout_report.style.format("{:,.0f}"), 
            #use_container_width=False
            width="content")

        # --- 9. CURRENT BALANCES ---
        st.divider()
        st.subheader("💰 Current Account Balances")

        cursor.execute("""
            SELECT "DATE", "CASH_BAL", "MANDIRI_BAL"
            FROM "RECORDS"
            ORDER BY "ID" DESC
            LIMIT 1
        """)

        latest = cursor.fetchone()

        if latest:
            last_date, cash_bal, mandiri_bal = latest

            balance_df = pd.DataFrame({
                "ACCOUNT": ["CASH", "MANDIRI"],
                "BALANCE": [cash_bal, mandiri_bal]
            })

            st.caption(f"Balances as of: {last_date}")

            st.dataframe(
                balance_df.style.format({"BALANCE": "{:,.0f}"}),
                width="content",
                #use_container_width=False,
                hide_index=True
            )
        else:
            st.warning("No balance data available.")

    st.success("Reporting engine loaded successfully.")

#st.caption(f"Full app run: {time.time() - app_start:.3f} sec")

