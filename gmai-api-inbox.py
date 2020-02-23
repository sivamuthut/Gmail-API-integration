import sqlite3
import time
import json
import httplib2
import logging
import base64
import email

from apiclient import errors
from sqlite3 import Error
from tkinter import *
from tkinter import messagebox
from bs4 import BeautifulSoup
from apiclient.discovery import build
from oauth2client.client import AccessTokenCredentials

logger = logging.getLogger(__name__)

QUERY_TYPE = ["All", "Any"]
# FIELDS = ["Mail_From", "Subject", "Message", " Date"]
FIELDS = ["Mail_From", "Subject", " Date"]
PREDICATE_CHAR = ["Contains", "Not contains", "Equals", "Not equal"]
PREDICATE_DATE = ["Less than", "Greater than"]
ACTION = ['Mark as read', 'Mark as Unread']
MAPPING = [
    ("Contains", "LIKE"),
    ("Not contains", "NOT LIKE"),
    ("Not equal", "!="),
    ("Less than", "<"),
    ("Greater than", ">"),
    ("All", "AND"),
    ("Any", "OR"),
    ("Mark as read", {'action': 'read', 'label': {'removeLabelIds': ['UNREAD']}}),
    ("Mark as Unread", {'action': 'unread', 'label': {'addLabelIds': ['UNREAD']}})
]

RULES = []
RULE_INDEX = 0
OVER_FLOW = False
USER = None
AGAIN = True

with open('oauth-credential.json') as json_file:
    CREDENTIALS = json.load(json_file)


class Gmail():
    def __init__(self, user):
        self.service = self.Authenticate()
        self.user = user

    def Authenticate(self):
        acc_token = CREDENTIALS['access_token']
        user_agent = 'Mozilla/5.0 (Windows NT 6.1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/41.0.2228.0 Safari/537.36'
        credentials = AccessTokenCredentials(acc_token, user_agent)
        http = httplib2.Http()
        http = credentials.authorize(http)
        return build('gmail', 'v1', http=http)

    def GetMimeMessage(self, query):
        try:
            response = self.service.users().messages().list(userId=self.user, q=query).execute()
            messages = response['messages']
            # Enable it if you want message from all pages
            # while 'nextPageToken' in response:
            #     page_token = response['nextPageToken']
            #     response = self.service.users().messages().list(userId=user, q=query,
            #                                                pageToken=page_token).execute()
            #     messages.extend(response['messages'])
            mails = []
            print('{} messages were fetched'.format(len(messages)))
            for msg in messages:
                collect = (msg['id'],)
                content = self.service.users().messages().get(userId=self.user, id=msg['id']).execute()

                for (index, s) in enumerate(content['payload']['headers']):
                    if s['name'] == 'From':
                        m = re.search('<(.+?)>', s['value'])
                        if m:
                            collect += (m.group(1),)
                        else:
                            collect += (None,)
                    if s['name'] == 'Subject':
                        collect += (s['value'],)
                    if s['name'] == 'Date':
                        collect += (s['value'],)
                mails.append(tuple(collect))

                # Message part, still need to be optimized

                # if 'parts' in content['payload']:
                #     for part in content['payload']['parts']:
                #         if 'data' in part['body']:
                #             msg_str = base64.urlsafe_b64decode(part['body']['data'].encode('ASCII'))
                #
                #             mime_msg = email.message_from_string(str(msg_str))
                #
                #             soup = BeautifulSoup(str(mime_msg), parser='html')
                #             text = soup.find("div")
                #             clean = re.compile('<.*?>')
                #
                #             msg = re.sub(r'\xc2\xc0', ' ', re.sub(clean, '', str(text)))

                with open('mail-data.json', 'w') as f:
                    json.dump(mails, f)
            print("\tmessages were dumped to mail-data.json.")

        except errors.HttpError as error:
            print('An error occurred: %s' % error)

    def Modify(self, messages, msg_labels):
        for msg in messages:
            message = self.service.users().messages().modify(userId=self.user, id=msg[0], body=msg_labels).execute()


class SQLite():
    def __init__(self, db_file):
        self.connection = self.create_connection(db_file)
        self.cursor = self.connection.cursor()
        self.move_to_database()

    def create_connection(self, db_file):
        connection = None
        try:
            connection = sqlite3.connect(db_file)
            print("\tSqlite connection made.")
        except Error as e:
            print('Error in making sqlite connection: ', e)
        finally:
            return connection

    def create_table(self, create_table_sql):
        try:
            c = self.connection.cursor()
            c.execute(create_table_sql)
            print("\tTable created.")
        except Error as e:
            print('Error in creating table: ', e)

    def insert_message(self, msg):
        try:
            sql = ''' INSERT INTO inbox(id,mail_from,date,subject)
                      VALUES(?,?,?,?) '''
            cur = self.connection.cursor()
            cur.execute(sql, msg)
            return cur.lastrowid

        except Exception as e:
            print("\tError while inserting into db: ", str(e))

    def apply_rules(self):
        print("\tCoverting ruels to sql...")
        with open('rules.json') as json_file:
            rules = json.load(json_file)
        sql_query = "SELECT id FROM inbox WHERE "
        for (index, rule) in enumerate(rules['conditions']):
            sql_query += "{} {} '{}' {} ".format(rule['field'].lower(),
                                                 dict(MAPPING).get(rule['predicate']),
                                                 rule['value'] if rule['predicate'] not in ["Contains",
                                                                                            "Not Contains"] else "%{}%".format(
                                                     rule['value']),
                                                 ';' if index + 1 == len(rules['conditions']) else dict(MAPPING).get(
                                                     rules['type'])
                                                 )
        self.cursor.execute(sql_query)
        obeying_rules = self.cursor.fetchall()
        print("\t {} messages were fetched with : {}".format(len(obeying_rules), sql_query))
        # self.connection.close()
        return obeying_rules, rules['action']

    def move_to_database(self):
        sql_create_inbox_table = """ CREATE TABLE IF NOT EXISTS inbox (
                                            id int PRIMARY KEY,
                                            mail_from text NOT NULL,
                                            date date,
                                            subject text
                                        ); """

        # create tables
        if self.connection is not None:
            # create projects table
            self.create_table(sql_create_inbox_table)

            # insert message into inbox

            with open('mail-data.json') as json_file:
                data = json.load(json_file)
            for msg in data:
                self.insert_message(tuple(msg))
            print("\t messages moved to db.")


class GUI():
    def __init__(self):
        pass

    def result(self, alert_message):
        result = Tk()
        result.title('Here is the result!')
        result.geometry("650x300")

        # Query type
        Label(result, text=alert_message).place(x=250, y=100)

        submit = Button(result, text="Try Again", pady=7, fg="white", bg="blue", command=result.destroy)
        submit.place(x=320, y=150)

        def quit():
            global AGAIN
            result.destroy()
            AGAIN = False

        cancel = Button(result, text="Ok", pady=7, command=quit)
        cancel.place(x=250, y=150)
        result.mainloop()

    def get_user(self):
        global USER
        start = Tk()
        start.title('Hi, Introduce Yourself!')
        start.geometry("650x300")

        # Query type
        Label(start, text="Your Mail Id").place(x=60, y=50)

        # Action
        USER = StringVar()
        Entry(start, textvariable=USER).place(x=150, y=50)

        # Footer
        def check_input():
            if re.match(r"[^@]+@[^@]+\.[^@]+", USER.get()):
                start.destroy()
            else:
                messagebox.showinfo("Invalid Input", "Need Valid Mail Id!")

        submit = Button(start, text="Read My Inbox", pady=7, fg="white", bg="blue", command=check_input)
        submit.place(x=320, y=100)
        cancel = Button(start, text="Cancel", pady=7, command=start.destroy)
        cancel.place(x=250, y=100)
        Label(start,
              text="Note: Before submitting, make sure oauth credentials were added in  oauth-credential.json").place(
            x=50, y=200)
        start.mainloop()

    def add_rule(self):
        global RULE_INDEX, RULES, root, OVER_FLOW
        if not OVER_FLOW:
            RULES.append({
                'field': None,
                'predicate': None,
                'value': None
            })

            # Rules
            RULES[RULE_INDEX]['field'] = StringVar()
            RULES[RULE_INDEX]['field'].set(FIELDS[0])
            field_btn = OptionMenu(root, RULES[RULE_INDEX]['field'], *FIELDS)
            field_btn.grid(row=RULE_INDEX + 3, column=4)

            RULES[RULE_INDEX]['predicate'] = StringVar()
            RULES[RULE_INDEX]['predicate'].set(PREDICATE_CHAR[0])
            predicate_btn = OptionMenu(root, RULES[RULE_INDEX]['predicate'], *PREDICATE_CHAR)
            predicate_btn.grid(row=RULE_INDEX + 3, column=5)

            RULES[RULE_INDEX]['value'] = StringVar()
            value = Entry(root, textvariable=RULES[RULE_INDEX]['value'])
            value.grid(row=RULE_INDEX + 3, column=6)
            if RULE_INDEX + 1 < len(FIELDS):
                Button(root, text=" + ", command=self.add_rule).grid(row=RULE_INDEX + 3, column=8)

                def remove_rule():
                    field_btn.grid_forget()
                    predicate_btn.grid_forget()
                    value.grid_forget()
                    RULE_INDEX -= 1

                Button(root, text=" - ", command=remove_rule).grid(row=RULE_INDEX + 3, column=7)

                RULE_INDEX += 1
            else:
                OVER_FLOW = True
        else:
            messagebox.showinfo("Limit Exceeded", "Reached maximum of {} rules!".format(len(FIELDS)))

    def show_GUI(self):
        global root
        root = Tk()
        root.title('My Inbox with Gmail-API')
        root.geometry("1000x700")

        # Query type
        query_type = StringVar()
        query_type.set(QUERY_TYPE[0])
        Label(root, text="If").grid(row=1, column=1)
        Label(root, text=" of the following condition").grid(row=1, column=3)
        OptionMenu(root, query_type, *QUERY_TYPE).grid(row=1, column=2)

        # Rules
        self.add_rule()

        # Action
        Label(root, text="Perform the Following action").grid(row=7, column=3)
        action = StringVar()
        action.set(ACTION[0])
        OptionMenu(root, action, *ACTION).grid(row=8, column=4)

        # Footer
        submit = Button(root, text="Ok", pady=7, fg="white", bg="blue", command=root.destroy)
        submit.grid(row=9, column=8)
        cancel = Button(root, text="Cancel", pady=7, command=root.destroy)
        cancel.grid(row=9, column=7)

        root.mainloop()
        rules = {
            'type': query_type.get(),
            'conditions': [],
            'action': action.get()
        }
        for r in RULES:
            rules['conditions'].append(
                {'field': r['field'].get(), 'predicate': r['predicate'].get(), 'value': r['value'].get()})

        with open('rules.json', 'w') as f:
            json.dump(rules, f)

        # with open('rules.json') as json_file:
        #     data = json.load(json_file)
        #     for p in data:
        #        print(p)


def main():
    global AGAIN
    ui = GUI()

    # Get Mail Id from user
    ui.get_user()
    user = USER.get()

    if user:
        # Read Inbox and dump in mail-data.json
        print('Fetching Inbox...')
        gmail = Gmail(user=user)
        gmail.GetMimeMessage(query='')

        # Get the data to Sqlite
        print('Storing to DB...')
        database = r"C:\sqlite\db\pythonsqlite.db"
        db = SQLite(database)

        # Get Conditions from user
        print("Waiting for input...")
        while AGAIN:
            global RULES, RULE_INDEX, OVER_FLOW
            ui.show_GUI()

            # Apply Rules
            obeying_rules, action = db.apply_rules()
            if obeying_rules:
                gmail.Modify(messages=obeying_rules, msg_labels=dict(MAPPING).get(action)['label'])
                ui.result('{} messages marked as {} !'.format(len(obeying_rules), dict(MAPPING).get(action)['action']))
            else:
                ui.result('Sorry..! No matching found...!')
            RULES = []
            RULE_INDEX = 0
            OVER_FLOW = False


if __name__ == "__main__":
    main()
