#!/usr/bin/env python3
# This is a generator of test cases
# Turn cases in directory ../suites/0_stateless/* into sqllogictest format
import os
import re
import copy
import logging

import mysql.connector

from config import config, http_config
from http_connector import HttpConnector, format_result

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

suite_path = "../suites/0_stateless/"
logictest_path = "./suites/gen/"

error_regex = r"(?P<statement>.*) -- {ErrorCode (?P<expectError>.*)}"
query_statment_first_words = ["select", "show", "explain", "describe"]

STATEMENT_OK = """statement ok
{statement}

"""

STATEMENT_ERROR = """statement error {error_id}
{statement}

"""

STATEMENT_QUERY = """statement query {query_options}
{statement}

{results}
"""

# results_string looks like, result is seperate by space.
# 1 1 1
RESULTS_TEMPLATE = """----  {labels}
{results_string}"""

http_client = HttpConnector()
http_client.connect(**http_config)
cnx = mysql.connector.connect(**config)
mysql_client = cnx.cursor()

def mysql_fetch_results(sql):
    mysql_client.execute(sql)
    r = mysql_client.fetchall()
    ret = ""
    for row in r:
        rowlist = []
        for item in row:
            rowlist.append(str(item))
        ret = ret + " ".join(rowlist) + "\n"
    return ret

def first_word(text):
    return text.split()[0]

def get_error_statment(line):
    return re.match(error_regex, line, re.MULTILINE | re.IGNORECASE)

def get_all_cases():
    # copy from databend-test 
    def collect_subdirs_with_pattern(cur_dir_path, pattern):
        return list(
            # Make sure all sub-dir name starts with [0-9]+_*.
            filter(lambda fullpath: os.path.isdir(fullpath) and \
                   re.search(pattern, fullpath.split("/")[-1]),
                   map(lambda _dir: os.path.join(cur_dir_path, _dir),
                       os.listdir(cur_dir_path))))

    def collect_files_with_pattern(cur_dir_path, patterns):
        return list(
            filter(
                lambda fullpath: os.path.isfile(fullpath) and os.path.splitext(
                    fullpath)[1] in patterns.split("|"),
                map(lambda _dir: os.path.join(cur_dir_path, _dir),
                    os.listdir(cur_dir_path))))

    def get_all_tests_under_dir_recursive(suite_dir):
        all_tests = copy.deepcopy(
            collect_files_with_pattern(suite_dir, ".sql|.sh|.py"))
        # Collect files in depth 0 directory.
        sub_dir_paths = copy.deepcopy(
            collect_subdirs_with_pattern(suite_dir, "^[0-9]+"))
        # Recursively get files from sub-directories.
        while len(sub_dir_paths) > 0:
            cur_sub_dir_path = sub_dir_paths.pop(0)

            all_tests += copy.deepcopy(
                collect_files_with_pattern(cur_sub_dir_path, ".sql|.sh|.py"))

            sub_dir_paths += copy.deepcopy(
                collect_subdirs_with_pattern(cur_sub_dir_path, "^[0-9]+"))
        return all_tests

    return get_all_tests_under_dir_recursive(suite_path)

def parse_cases(sql_file):
    target_dir = os.path.dirname(str.replace(sql_file,suite_path,logictest_path))
    case_name = os.path.splitext(os.path.basename(sql_file))[0]
    log.info("Write test case to path: {}, case name is {}".format(target_dir, case_name))

    content_output = ""
    f = open(sql_file)
    for line in f.readlines():
        # error
        errorStatment = get_error_statment(line)
        if errorStatment != None:
            content_output = content_output + STATEMENT_ERROR.format(
                error_id = errorStatment.group("expectError"),
                statement = errorStatment.group("statement")
                )
            continue

        statement = line.strip()
        if str.lower(first_word(line)) in query_statment_first_words:      
            # query
            
            http_results = format_result(http_client.fetch_all(statement))
            query_options = http_client.get_query_option()

            mysql_results = mysql_fetch_results(statement)
            
            case_results = RESULTS_TEMPLATE.format(
                results_string = mysql_results, labels = "")  # mysql as baseline
            if mysql_results != http_results:
                case_results = case_results + "\n" + RESULTS_TEMPLATE.format(
                results_string = http_results, labels = "http")

            content_output = content_output + STATEMENT_QUERY.format(
                query_options = query_options,
                statement = statement,
                results = case_results
            )
        else:
            # ok
            try:
                # use for sql session, ignore results
                mysql_client.excute(line)
                http_client.query_with_session(line)
            except Exception as err:
                log.warn("statement {} excute error,msg {}".format(statement, str(err)))
                pass

            content_output = content_output + STATEMENT_OK.format(statement = statement)

    f.close()
    if not os.path.exists(target_dir):
        os.makedirs(target_dir)

    caseFile = open(os.path.join(target_dir,case_name), 'w')
    caseFile.write(content_output)
    caseFile.close()


def main():
    all_cases = get_all_cases()

    for file in all_cases:
        # .result will be ignore
        if '.result' in file or '.result_filter' in file:
            continue  
        
        # .py .sh will be ignore, need log
        if ".py" in file or ".sh" in file:
            log.warn("test file {} will be ignore".format(file))
            continue

        log.info("Start parse test file {}".format(file))
        parse_cases(file)
        break
    

if __name__ == '__main__':
    log.info("Start generate sqllogictest suites from path: {} to path: {}".format(suite_path, logictest_path))
    main()
