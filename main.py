import os.path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
import json
import requests
from tqdm import tqdm
import configparser
import time


class VK:

   def __init__(self, access_token, user_id, version='5.131'):
       self.token = access_token
       self.id = user_id
       self.version = version
       self.params = {'access_token': self.token, 'v': self.version}

   def users_id(self):
       url = 'https://api.vk.com/method/users.get'
       params = {'user_ids': self.id}
       response = requests.get(url, params={**self.params, **params})
       return response.json()['response'][0]['id']

   def users_photo_get(self):
       url = 'https://api.vk.com/method/photos.get'
       headers = {'Authorization': 'Bearer ' + self.token}
       params = {'v': self.version,
                 'owner_id': self.users_id(),
                 'album_id': 'profile',
                 'extended': 1,
                 'photo_sizes': 1,
                 'rev': 1}
       response = requests.get(url, params=params, headers=headers)
       return response

   def users_photo_url(self):
       photo_dict = {}
       photos_list = self.users_photo_get().json()['response']['items']
       for photo in photos_list:
           photo_likes = str(photo['likes']['count'])
           photo_upload_date = str(photo['date'])

           for size_max in ['w', 'z', 'y', 'x', 'r', 'q', 'p']:
               photo_url = []
               photo_url, photo_size = [size['url'] for size in photo['sizes'] if size['type'] == size_max], size_max
               if photo_url != []:
                   break
           photo_dict[photo_url[0]] = [photo_likes,  photo_upload_date, photo_size]
       return photo_dict

class YaUploader:

    def __init__(self, yandex_token, vk_object, num_photo=5):
        self.token = yandex_token
        self.vk_photo_list = vk_object.users_photo_url()
        self.vk_id = vk_object.id
        if num_photo > len(self.vk_photo_list):
            self.num_photo = len(self.vk_photo_list)
        else:
            self.num_photo = num_photo
        self.upload_folder = self.path_create()
        self.list_of_files = self.get_list_of_files()

    def _headers(self):
        return {'Content-Type': 'application/json',
                'Authorization': 'OAuth '+self.token}

    def path_create(self):
        url = 'https://cloud-api.yandex.net/v1/disk/resources'
        params = {'path': 'Резервное хранилище/'}
        if requests.get(url=url, params=params, headers=self._headers()).status_code == 404:
            requests.put(url=url, params=params, headers=self._headers())

        params = {'path': 'Резервное хранилище/' + self.vk_id}
        if requests.get(url=url, params=params, headers=self._headers()).status_code == 404:
            requests.put(url=url, params=params, headers=self._headers())
        return 'Резервное хранилище/' + self.vk_id

    def get_list_of_files(self):
        list_of_files = []
        params = {'path': 'Резервное хранилище/' + self.vk_id}
        response = requests.get(url='https://cloud-api.yandex.net/v1/disk/resources',
                                params={'path': self.upload_folder},
                                headers=self._headers())
        for photo in response.json()['_embedded']['items']:
            list_of_files += [photo['name']]
        return list_of_files

    def json_photo_dict(self, photo_name, photo_size):
         json_photo = {"file_name": photo_name,
                       "size": photo_size
                       }
         return json_photo

    def ya_upload(self):
        counter = 0
        json_data = {'photos': [],
                     'yandex_disc': 'disk:/Резервное хранилище/' + self.vk_id}
        url = 'https://cloud-api.yandex.net/v1/disk/resources/upload'
        for photo in tqdm(self.vk_photo_list, desc='Загрузка на Яндекс.Диск: ', colour='#99ff99', total=self.num_photo,
                          ncols=100):
            if counter >= self.num_photo:
                break
            photo_name = self.vk_photo_list[photo][0]+"_"+self.vk_photo_list[photo][1]+".jpg"
            params = {'path': 'Резервное хранилище/' + self.vk_id+'/' + photo_name,
                      'url': photo}
            if photo_name not in self.list_of_files:
                requests.post(url=url, params=params, headers=self._headers())
            json_data['photos'] += [self.json_photo_dict(photo_name, self.vk_photo_list[photo][2])]
            counter += 1
        if not os.path.exists('logs'):
            os.makedirs('logs')
        with open('logs/' + self.vk_id + '_yandex.json', 'w', encoding='utf-8') as logfile:
            json.dump(json_data, logfile, ensure_ascii=False, indent=4)
        return


class GoogleUploader:

    def __init__(self, vk_object, num_photo=5):
        self.token = self.get_google_token()
        self.headers = {"Authorization": "Bearer " + self.token,
                        "Accept": "application/json"}
        self.permissionID = self.get_permissionID()
        self.vk_photo_list = vk_object.users_photo_url()
        self.vk_id = vk_object.id
        if num_photo > len(self.vk_photo_list):
            self.num_photo = len(self.vk_photo_list)
        else:
            self.num_photo = num_photo
        self.dict_of_folders = self.get_list_of_folders()
        self.upload_folder_id = self.create_folder()
        self.list_of_files = self.get_list_of_files()

    def get_google_token(self):
        SCOPES = ['https://www.googleapis.com/auth/drive.metadata.readonly',
                  'https://www.googleapis.com/auth/drive']
        creds = None
        if os.path.exists('google_token.json'):
            creds = Credentials.from_authorized_user_file('google_token.json', SCOPES)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    'google_credentials.json', SCOPES)
                creds = flow.run_local_server(port=0)
            with open('google_token.json', 'w') as token:
                token.write(creds.to_json())
        with open('google_token.json') as f:
            token = json.load(f)["token"]
        return token

    def get_permissionID(self):
        headers = self.headers
        params = {"fields": "user"}
        url = 'https://www.googleapis.com/drive/v3/about'
        response = requests.get(url, headers=headers, params=params)
        return response.json()["user"]["permissionId"]

    def get_list_of_folders(self):
        dict_of_files = {}
        headers = self.headers
        params = {"q": f"mimeType = 'application/vnd.google-apps.folder' and trashed = false and '{self.permissionID}' in owners",
                  "fields": "files(name, id)"}
        url = 'https://www.googleapis.com/drive/v3/files/'
        response = requests.get(url, headers=headers, params=params)

        for i in response.json()['files']:
            dict_of_files[i['name']] = i['id']

        return dict_of_files

    def get_list_of_files(self):
        list_of_files = []
        headers = self.headers
        params = {"q": f"mimeType='image/jpeg' and '{self.upload_folder_id}' in parents and trashed = false and '{self.permissionID}' in owners",
                  "fields": "files(name)"}
        url = 'https://www.googleapis.com/drive/v3/files/'
        response = requests.get(url, headers=headers, params=params)
        if response.status_code != 400:
            for i in response.json()['files']:
                list_of_files += [i['name']]
        return list_of_files

    def create_folder(self):
        if self.vk_id not in self.dict_of_folders:
            url = 'https://www.googleapis.com/drive/v3/files'
            headers = self.headers
            metadata = {'name': self.vk_id,
                        'mimeType': 'application/vnd.google-apps.folder'}
            response = requests.post(url, headers=headers, data=json.dumps(metadata))
            time.sleep(2)
            upload_folder_id = response.json()['id']

        else:
            upload_folder_id = self.dict_of_folders[self.vk_id]

        return upload_folder_id

    def json_photo_dict(self, photo_name, photo_size):
         json_photo = {"file_name": photo_name,
                       "size": photo_size}
         return json_photo

    def google_upload(self):
        counter = 0
        json_data = {'photos': [],
                     'google_disc': 'disk:/' + self.vk_id}
        url = "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart"

        for photo in tqdm(self.vk_photo_list, desc='Загрузка на Google.Drive: ', colour='#99ff99', total=self.num_photo,
                          ncols=100):
            if counter >= self.num_photo:
                break
            photo_name = self.vk_photo_list[photo][0] + "_" + self.vk_photo_list[photo][1] + ".jpg"
            if photo_name not in self.list_of_files:
                photo_url = photo

                response_photo = requests.get(photo_url).content

                headers = self.headers
                params = {"name": photo_name,
                          "parents": [self.upload_folder_id]}
                files = {"data": ("metadata", json.dumps(params), "application/json; charset=UTF-8"),
                         "file": response_photo}
                response = requests.post(url=url, headers=headers,
                                         files=files)
                json_data['photos'] += [self.json_photo_dict(photo_name, self.vk_photo_list[photo][2])]
            counter += 1

        if not os.path.exists('logs'):
            os.makedirs('logs')
        with open('logs/' + self.vk_id + '_google.json', 'w', encoding='utf-8') as logfile:
            json.dump(json_data, logfile, ensure_ascii=False, indent=4)
        return


if __name__ == '__main__':

    config = configparser.ConfigParser()
    config.read("config.ini")

    vk_access_token = config["VK"]["access_token"]
    VK_user_id_to_upload = input('Введите ID пользователя VK: ')  # ID пользователя VK который неоюходимо скачать
    yandex_token = input('Введите токен Яндекса: ')

    vk = VK(vk_access_token, VK_user_id_to_upload)
    ya = YaUploader(yandex_token, vk, num_photo=5)
    ggl = GoogleUploader(vk, num_photo=5)

    ya.ya_upload()
    ggl.google_upload()
