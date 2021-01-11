import itertools
import time
from datetime import datetime
from selenium import webdriver
from selenium.webdriver import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import traceback
import re
import json
import os

CACHE_PATH = "cache"
BATCH_SIZE = 40
UNLOAD = True
CHECK_ONCE_EVERY = 50

os.makedirs(CACHE_PATH, exist_ok=True)
options = webdriver.ChromeOptions()
options.add_argument(r"--user-data-dir={}".format(os.path.abspath(CACHE_PATH)))

driver = webdriver.Chrome(chrome_options=options)
driver.get("https://support.samsungcloud.com/")

input("Please sign in and navigate to the gallery page.\n"
      "Note: you may want to change the download folder in Chrome as well.\n"
      "Press enter here once you are done.")


def _scroll_to_if_needed(elem):
    driver.execute_script(r"arguments[0].scrollIntoViewIfNeeded();", elem)


def _scroll_to_smooth(elem):
    driver.execute_script(r"arguments[0].scrollIntoView({behavior:'smooth'});", elem)


def _remove_from_dom(elem):
    driver.execute_script(r"arguments[0].remove();", elem)


def get_listitem_by_index(index_, unload=True, max_items=160):
    """
    index is computed using the tags themselves
    (accounts for if the counting in the DOM is not contiguous
    in practice, the images can be assumed to be in-order, persistent in the DOM and contiguous,
    and so get_lixstitem_by_index_fast may be used)
    """
    index = index_ + 1
    last_computed_index = 0
    last_scrolled = 0
    while True:
        sec_psum = 0
        last_sec = 0
        last_num = 0
        listitems = driver.find_elements_by_xpath("//div[@role='listitem']")

        if unload:
            # keep last `max_items` listitems only
            count = 0
            for listitem in listitems[:-max_items]:
                _remove_from_dom(listitem)
                count += 1
            print("Unloaded {}".format(count))
            listitems = listitems[-max_items:]

        for listitem in listitems:
            sec, num = map(int, re.match(r"gallerySelector(\d+)_(\d+)", listitem.get_attribute("id")).groups())

            if sec > last_sec:
                sec_psum += last_num
                last_sec = sec
            last_num = num

            computed_index = sec_psum + num

            if computed_index == index:
                return listitem
            if computed_index > last_computed_index:
                last_computed_index = computed_index
        else:
            # scroll down to the last img (to load more underneath)
            if last_computed_index != last_scrolled:
                _scroll_to_smooth(listitem)
                last_scrolled = last_computed_index


_unload_offset = 0


def get_listitem_by_index_fast(index, max_items=105):
    global _unload_offset

    last_len = 0
    no_change_count = 0  # number of times count has consecutively been the same
    while True:
        listitems = driver.find_elements_by_xpath("//div[@role='listitem']")

        cur_len = _unload_offset + len(listitems)
        if index >= cur_len:
            if cur_len != last_len:
                _scroll_to_smooth(listitems[-1])
                last_len = cur_len
                no_change_count = 0
            else:
                no_change_count += 1
                if no_change_count > 30:
                    print("PROBABLY REACHED MAX!! cur_len: ", cur_len)
                    raise RuntimeError
            time.sleep(0.4)
        else:
            return listitems[index - _unload_offset]


def select_listitem(listitem):
    # hover over listitem
    ActionChains(driver).move_to_element(listitem).perform()

    # click check circle
    listitem_id = listitem.get_attribute("id")
    check_circle = WebDriverWait(driver, 20).until(EC.element_to_be_clickable((
        By.XPATH,
        "//*[@id='{}']".format(listitem_id.replace("gallerySelector", "gallerySelectorCircle")))
    ))
    check_circle.click()


def select_range(start_index, n):
    """
    :return: successfully selected range without truncating or not
    """
    for i in range(start_index, start_index + n):
        try:
            listitem = get_listitem_by_index_fast(i)
            select_listitem(listitem)
        except RuntimeError:
            return False
    return True


def download_selected(wait_for_toast_fade=True):
    fail_count = 1
    while True:
        try:
            WebDriverWait(driver, 20).until(
                EC.element_to_be_clickable((By.XPATH, "//*[@id='gallerySelectedItemBtnDownload']"))).click()
            # long wait because downloading (internet could be slow, etc)
            toast = WebDriverWait(driver, 10 * 60).until(
                EC.visibility_of_element_located((By.XPATH, "//*[@id='toast-root']")))
            toast_txt = toast.text

            if wait_for_toast_fade:
                WebDriverWait(driver, 40).until_not(
                    EC.visibility_of_element_located((By.XPATH, "//*[@id='toast-root']")))

            if 'downloaded' in toast_txt:
                print("downloaded")
            elif 'not be downloaded' in toast_txt:
                print('could not download')
                raise RuntimeError
            else:
                print("Unknown toast message: ", toast_txt)
                raise RuntimeError
            break
        except:
            print("Could not download!!")
            traceback.print_exc()
            time.sleep(10 * fail_count)
            fail_count += 1

            if fail_count > 3:
                raise


def download(start_index=0, batch_size=40, only_one_batch=False, reload=True):
    # check_gen = itertools.count(0, CHECK_ONCE_EVERY)
    # next_check = next(check_gen)

    cur_index = start_index
    last_index = start_index
    while True:
        try:
            print("{} -- Trying to download starting at: {}".format(datetime.utcnow().strftime("%x %X"), cur_index))

            success = select_range(cur_index, batch_size)
            download_selected()

            unload()

            if not success:
                print("(Hopefully) reached end!")
                break
            else:
                if only_one_batch:
                    return
                cur_index += batch_size
        except:
            if reload:
                print("Fatal error! Reloading and retrying in a bit...")
                time.sleep(5)
                driver.get("https://support.samsungcloud.com/#/gallery")
                global _unload_offset
                _unload_offset = 0
                unload()
            else:
                continue
        finally:
            print("{} -- Downloaded {}-{}".format(datetime.utcnow().strftime("%x %X"), last_index, cur_index))
            last_index = cur_index


def _download_file(name, url):
    driver.execute_script("""
    var link = document.createElement("a");
    link.download = arguments[0];
    link.target = "_blank";

    link.href = arguments[1];
    document.body.appendChild(link);
    link.click();

    document.body.removeChild(link);
    delete link;
    """, name, url)


DATA_TEST_IMAGE = "data:image/png;base64,iVBORw0KGV9Jm2u7rmsCe65wKzPTw5jtS38n2tVEGiDtbLrcW77HPEwrJM2Ej2yFNYwNQCeaxcW+vr6xsbGV9Jm2u7rmsCe65wKzPTw5jtS38n2tVEGiDtbLrcW77HPEwrJM2Ej2yFNYwN+DLgjH2m5c8emE66pjdExmgep47BAdKTrCJ7ZEkZhRUqn92f0MaTubtfeMh/QGHANEREREREREREREtIJJ0xbH299kp8l8FaGtLdTQ19HjofxZlJ0m1+eBKZcikd9PWtXC5DoDotRO04B9YOvFIXnHiSgDznyvEWLRDTty2Ej8fUgrwm3Xjt1CJ7ZFWz/pHM2CVte0lS8g2eDe6prOyqPglhzROL+Xye4tmT4WvRcQ2/m81p+/rdguOi8Hc5L/8Qk4vhZzy08DduGt9eVQyP2qoTM1zi0/uf4hvBWf5c77e69Gf798y08L7j0RERERERERERH9P99ZpSVRivB/rgAAAABJRU5ErkJggg=="


def _download_multiple_prompt(n=5):
    for i in range(n):
        _download_file("test", DATA_TEST_IMAGE)
    input("Please allow downloading multiple files. Press enter here once done")


def unload():
    if UNLOAD:
        global _unload_offset
        listitems = driver.find_elements_by_xpath("//div[@role='listitem']")
        # keep last `max_items` listitems only
        for listitem in listitems[:-105]:
            _remove_from_dom(listitem)
            _unload_offset += 1
        # listitems = listitems[-max_items:]
        time.sleep(2)
        print("Unload offset now: {}".format(_unload_offset))


def download_thumbnails(start_index=0, reload=True):
    _download_multiple_prompt()

    cur_index = start_index

    while True:
        try:
            fail_count = 0
            while True:
                if cur_index % CHECK_ONCE_EVERY == 0:
                    download(cur_index, 2, True)
                    unload()

                try:
                    print("{}: Trying to download thumb #{:05d}".format(datetime.utcnow().strftime("%x %X"), cur_index))
                    listitem = get_listitem_by_index_fast(cur_index)
                    _scroll_to_if_needed(listitem)
                    thumb = WebDriverWait(driver, 30).until(EC.presence_of_element_located((
                        By.XPATH,
                        "//div[@role='listitem'][@id='{}']/.//img[@role='presentation'][not(@src='')]".format(
                            listitem.get_attribute("id"))
                    )))

                    src = thumb.get_attribute("src")
                    _download_file("{:05d}".format(cur_index), src)
                    print(
                        "{}: Downloaded thumb #{:05d}: {}".format(datetime.utcnow().strftime("%x %X"), cur_index, src))

                    cur_index += 1
                    break
                except RuntimeError:
                    raise
                except:
                    traceback.print_exc()
                    time.sleep(5)
                    fail_count += 1
                    if reload:
                        if fail_count > 5:
                            print("{}: Fatal error! Reloading and retrying in a bit...".format(
                                datetime.utcnow().strftime("%x %X")))
                            fail_count = 0
                            time.sleep(5)
                            driver.get("https://support.samsungcloud.com/#/gallery")
                            global _unload_offset
                            _unload_offset = 0
                            unload()
        except RuntimeError:
            print("End reached!")
            break


# download_thumbnails(start_index=0)
download(start_index=0)
