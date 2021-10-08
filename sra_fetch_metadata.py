#!/usr/bin/env python

import argparse
import csv
import json
import re
import requests

from xml.etree import cElementTree as ElementTree

from simplejson.scanner import JSONDecodeError


class XmlListConfig(list):
    def __init__(self, aList):
        for element in aList:
            if element is not None:
                if len(element) == 0:
                    self.append(XmlDictConfig(element))
                # treat like dict
                elif len(element) == 1 or element[0].tag != element[1].tag:
                    self.append(XmlDictConfig(element))
                # treat like list
                elif element[0].tag == element[1].tag:
                    self.append(XmlListConfig(element))
            elif element.text:
                text = element.text.strip()
                if text:
                    self.append(text)


class XmlDictConfig(dict):
    '''
    https://stackoverflow.com/a/5807028
    Example usage:

    >>> tree = ElementTree.parse('your_file.xml')
    >>> root = tree.getroot()
    >>> xmldict = XmlDictConfig(root)

    Or, if you want to use an XML string:

    >>> root = ElementTree.XML(xml_string)
    >>> xmldict = XmlDictConfig(root)

    And then use xmldict for what it is... a dict.
    '''
    def __init__(self, parent_element):
        if parent_element.items():
            self.update(dict(parent_element.items()))
        for element in parent_element:
            if element:
                # treat like dict - we assume that if the first two tags
                # in a series are different, then they are all different.
                if len(element) == 1 or element[0].tag != element[1].tag:
                    aDict = XmlDictConfig(element)
                # treat like list - we assume that if the first two tags
                # in a series are the same, then the rest are the same.
                else:
                    # here, we put the list in dictionary; the key is the
                    # tag name the list elements all share in common, and
                    # the value is the list itself 
                    aDict = {element[0].tag: XmlListConfig(element)}
                # if the tag has attributes, add those to the dict
                if element.items():
                    aDict.update(dict(element.items()))
                self.update({element.tag: aDict})
            # this assumes that if you've got an attribute in a tag,
            # you won't be having any text. This may or may not be a 
            # good idea -- time will tell. It works for the way we are
            # currently doing XML configuration files...
            elif element.items():
                self.update({element.tag: dict(element.items())})
            # finally, if there are no child tags and no attributes, extract
            # the text
            else:
                self.update({element.tag: element.text})


def parse_xml(xml_string):
    parsed_xml = {}
    root = ElementTree.fromstring(xml_string)
    parsed_xml = XmlDictConfig(root)
    return parsed_xml


def print_experiment_csv(e):
    for run in e['runs']:
        print(','.join([
            run['acc'],
            e['Bioproject'],
            e['Experiment']['acc'],
            e['Experiment']['name'],
            e['Organism']['ScientificName'],
            e['Instrument']['ILLUMINA'],
            e['Submitter']['center_name'],
            e['Study']['acc'],
            e['Study']['name'],
            e['Sample']['acc'],
            e['Sample']['name'],
            e['Summary']['Statistics']['total_size'],
            e['Summary']['Statistics']['total_runs'],
            e['Summary']['Statistics']['total_spots'],
            e['Summary']['Statistics']['total_bases'],
            e['Library_descriptor']['LIBRARY_NAME'],
            e['Library_descriptor']['LIBRARY_STRATEGY'],
            e['Library_descriptor']['LIBRARY_SOURCE'],
            e['Library_descriptor']['LIBRARY_SELECTION'],
            
        ]))

    return None


def main(args):
    base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    project_query_params = {
        'db': 'sra',
        'retmode': 'json',
        'usehistory': 'y',
        'term': args.project_id,
    }

    project_query_webenv = None
    project_data = None
    project_response = requests.get(base_url + '/esearch.fcgi?', params=project_query_params)
    if project_response.status_code == 200:
        project_data = project_response.json()
        project_query_webenv = project_data['esearchresult']['webenv']

    biosample_data = None
    experiments = []
    intervals = range(0, args.max_samples + 1, 500)

    output_fields = [
        'run_accession',
        'bioproject_accession',
        'experiment_accession',
        'experiment_title',
        'organism_name',
        'instrument,submitter',
        'study_accession',
        'study_title',
        'sample_accession',
        'sample_title',
        'total_size_mb',
        'total_runs',
        'total_spots',
        'total_bases',
        'library_name',
        'library_strategy',
        'library_source',
        'library_selection'
    ]

    print(','.join(output_fields))
    
    for retstart in intervals:
        if project_query_webenv:
            biosample_query_params = {
                'db': 'sra',
                'retmode': 'json',
                'query_key': '1',
                'WebEnv': project_query_webenv,
                'retstart': retstart,
                'retmax': 500,
            }

            biosample_response = requests.get(base_url + '/esummary.fcgi?', params=biosample_query_params)
            if biosample_response.status_code == 200 and not re.search('\"error\":', biosample_response.text):
                try:
                    biosample_data = biosample_response.json()
                except JSONDecodeError as e:
                    print(json.dumps(biosample_query_params, indent=2))
                    print(biosample_response.text)
                    exit(1)

        try:
            uids = biosample_data['result']['uids']
        except KeyError as e:
            print(json.dumps(biosample_data, indent=2))
            exit(1)

        for uid in biosample_data['result']['uids']:
            expxml_str = '<root>' + biosample_data['result'][uid]['expxml'].strip() + '</root>'
            parsed_experiment = parse_xml(expxml_str)
            
            runs_str = '<root>' + biosample_data['result'][uid]['runs'].strip() + '</root>'
            parsed_runs = parse_xml(runs_str)
            parsed_experiment['runs'] = []
            parsed_experiment['runs'].append(parsed_runs['Run'])
            if "ILLUMINA" in parsed_experiment['Instrument'].keys():
                experiments.append(parsed_experiment)

    
        for experiment in experiments:
            print_experiment_csv(experiment)


    
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-p', '--project-id')
    parser.add_argument('-m', '--max-samples', default=5000)
    args = parser.parse_args()

    main(args)
