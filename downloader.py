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

DOWNLOAD_PATH = os.path.expanduser("~/Downloads/sams")
BATCH_SIZE = 40

driver = webdriver.Chrome()
driver.get("https://support.samsungcloud.com/")
input("Please sign in and navigate to the gallery page.\n"
      "Note: you may want to change the download folder in Chrome as well.\n"
      "Press enter here once you are done.")

def _scroll_to_if_needed(elem):
    driver.execute_script(r"arguments[0].scrollIntoViewIfNeeded();", elem)

def _scroll_to_smooth(elem):
    driver.execute_script(r"arguments[0].scrollIntoView({behavior:'smooth'});", elem)

def get_listitem_by_index(index_):
    """
    index is computed using the tags themselves
    (accounts for if the counting in the DOM is not contiguous
    in practice, the images can be assumed to be in-order, persistent in the DOM and contiguous,
    and so get_listitem_by_index_fast may be used)
    """
    index = index_ + 1
    last_computed_index = 0
    last_scrolled = 0
    while True:
        # calculate dict
        sec_psum = 0
        last_sec = 0
        last_num = 0
        for listitem in driver.find_elements_by_xpath("//div[@role='listitem']"):
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

def get_listitem_by_index_fast(index):
    last_len = 0
    no_change_count = 0  # number of times count has consecutively been the same
    while True:
        listitems = driver.find_elements_by_xpath("//div[@role='listitem']")
        cur_len = len(listitems)
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
            return listitems[index]

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
    for i in range(start_index, start_index+n):
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
            WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.XPATH, "//*[@id='gallerySelectedItemBtnDownload']"))).click()
            # long wait because downloading (internet could be slow, etc)
            toast = WebDriverWait(driver, 10*60).until(EC.visibility_of_element_located((By.XPATH, "//*[@id='toast-root']")))
            toast_txt = toast.text

            if wait_for_toast_fade:
                WebDriverWait(driver, 40).until_not(EC.visibility_of_element_located((By.XPATH, "//*[@id='toast-root']")))

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
            time.sleep(10*fail_count)
            fail_count += 1

            if fail_count > 3:
                raise

def download(start_index=0):
    cur_index = start_index
    last_index = start_index
    while True:
        try:
            print("{} -- Trying to download starting at: {}".format(datetime.utcnow().strftime("%x %X"), cur_index))

            success = select_range(cur_index, BATCH_SIZE)
            download_selected()

            if not success:
                print("(Hopefully) reached end!")
                break
            else:
                cur_index += BATCH_SIZE
        except:
            print("Fatal error! Reloading and retrying in a bit...")
            time.sleep(5)
            driver.get("https://support.samsungcloud.com/#/gallery")
        finally:
            print("{} -- Downloaded {}-{}".format(datetime.utcnow().strftime("%x %X"), last_index, cur_index))
            last_index = cur_index
download(start_index=4600)