# import libraries
import csv
from pathlib import Path
import time
from datetime import datetime
import re
from taumahi import *
from os import listdir, makedirs
from multiprocessing.dummy import Process, Pool as ThreadPool, Lock
from os.path import isfile, join, exists

indir = '1854-1987'
outdir = 'processed'
index_filename = 'hathivolumeURLs.csv'
volumeindex_fieldnames = ['retrieved', 'url', 'name',
                          'period', 'session', 'downloaded', 'processed']
dayindex_fieldnames = ['url', 'volume', 'date', 'reo', 'ambiguous', 'other',
                       'percent', 'retrieved', 'format', 'incomplete']
reo_fieldnames = ['url', 'volume', 'date', 'utterance', 'speaker', 'reo',
                  'ambiguous', 'other', 'percent', 'text']
# Processing the text is local resource intensive,
# therefore number of threads should be comparable to the CPU specs.
num_threads = 1
write_lock = Lock()


def get_file_list():
    volume_list = read_index_rows()
    file_list = [f for f in listdir(indir) if isfile(
        join(indir, f)) and f.endswith('.csv')]

    for v in volume_list:
        for f in file_list:
            if v['name'] == f[:f.index('.csv')] and not v['processed']:
                yield f, v


def read_index_rows():
    while True:
        rows = []
        with open(index_filename, 'r') as url_file:
            reader = csv.DictReader(url_file)
            for row in reader:
                rows.append(row)
            return rows


def process_csv_files():
    if not exists(outdir):
        makedirs(outdir)

    if not exists('hansardrāindex.csv'):
        with open('hansardrāindex.csv', 'w') as f:
            writer = csv.DictWriter(f, dayindex_fieldnames)
            writer.writeheader()
    if not exists('hansardreomāori.csv'):
        with open('hansardreomāori.csv', 'w') as f:
            writer = csv.DictWriter(f, reo_fieldnames)
            writer.writeheader()

    # with ThreadPool(num_threads) as pool:
    for name in map(process_csv, get_file_list()):
        i_rows = []
        r_rows = []
        with open('{}/{}rāindex.csv'.format(outdir, name), 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                i_rows.append(row)
        with open('{}/{}reomāori.csv'.format(outdir, name), 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                r_rows.append(row)
        with open('hansardrāindex.csv', 'a') as f:
            writer = csv.DictWriter(f, dayindex_fieldnames)
            writer.writerows(i_rows)
        with open('hansardreomāori.csv', 'a') as f:
            writer = csv.DictWriter(f, reo_fieldnames)
            writer.writerows(r_rows)


def process_csv(args):
    f = args[0]
    v = args[1]
    print('Extracting corpus from {}:'.format(f))

    volume = Volume(f, v)
    volume.process_pages()

    # Update the record of processed volumes:
    with write_lock:
        completion = 1
        rows = []
        for row in read_index_rows():
            if v['name'] == row['name']:
                row['processed'] = True
            rows.append(row)

        while True:
            with open(index_filename, 'w') as url_file:
                writer = csv.DictWriter(url_file, volumeindex_fieldnames)
                writer.writeheader()
                writer.writerows(rows)
            break
    return v['name']


class Volume(object):
    """docstring for Volume."""

    def __init__(self, filename, v):
        self.filename = filename
        self.day = {'format': 'OCR'}
        self.totals = {}
        self.row = {'utterance': 0}
        self.day['volume'] = self.row['volume'] = v['name']
        self.day['url'] = self.row['url'] = v['url']
        self.day['date'] = v['period']
        self.day['retrieved'] = v['retrieved']
        self.flag294 = int(self.row['volume'].isdigit()
                           and int(self.row['volume']) >= 294)
        self.flag410 = int(self.flag294 and int(self.row['volume']) >= 410)

    def process_pages(self):
        # Invoke this method from a class instance to process the debates.
        with open('{}/{}{}'.format(outdir, self.row['volume'], 'rāindex.csv'), 'w') as output:
            writer = csv.DictWriter(output, dayindex_fieldnames)
            writer.writeheader()
        with open('{}/{}{}'.format(outdir, self.row['volume'], 'reomāori.csv'), 'w') as output:
            writer = csv.DictWriter(output, reo_fieldnames)
            writer.writeheader()

        with open('{}/{}'.format(indir, self.filename), 'r') as kiroto:
            reader = csv.DictReader(kiroto)
            day = []
            for page in reader:
                if not (page['url'].endswith(('c', 'l', 'x', 'v', 'i')) or page['page'] == '1') and re.search('[a-zA-Z]', page['text']):
                    day = self.__process_page(page, day)

    def __process_page(self, page, day):
        text = page['text']
        looped = 0

        while True:
            nextday = date_pattern[self.flag294].search(text)
            if nextday:
                header = previoustext = None
                if not looped:
                    header = header_pattern.match(text[:nextday.start()])
                if header:
                    previoustext = text[header.end():nextday.start()]
                else:
                    previoustext = text[:nextday.start()]
                if previoustext:
                    day.append(previoustext.strip())
                self.__process_day(day)

                day = []
                self.row['date'] = self.day['date'] = clean_whitespace(
                    nextday.group(0))
                self.row['url'] = self.day['url'] = page['url']
                self.day['retrieved'] = page['retreived']
                self.row['utterance'] = 0
                text = text[nextday.end():]
                looped += 1
            else:
                if not looped:
                    header = header_pattern.match(text)
                    if header:
                        text = text[header.end():]
                if text:
                    day.append(text.strip())
                break
        return day

    def __process_day(self, day):
        text = '\n'.join(day)

        # Remove hyphenated line breaks
        text = re.sub('(?<=[a-z]) *-\n+ *(?=[a-z])', '', text)
        # Remove name lists, ayes and noes
        # Remove lines with no letters, short lines, single word lines and lines of punctuation, capitals, digits
        regex = ['([A-Z][ a-zA-Z.]+, ){2}[A-Z][ a-zA-Z.]+\.', '(AYE|Aye|NOE|Noe)[^\n]*',
                 '[^A-Za-z]*', '[^\n]{1,2}', '[ \-\d,A-Z.?!:]+', '[a-zA-Z]+', ]
        for r in regex:
            text = re.sub('(?<=\n){}\n'.format(r), '', text)

        # Reset totals then process text:
        self.totals = {'reo': 0, 'ambiguous': 0, 'other': 0}
        self.__process_paragraphs(text)

        # Write day statistics
        if sum(self.totals.values()) > 50:
            self.day['percent'] = get_percentage(**self.totals)
            self.day.update(self.totals)
            with open('{}/{}{}'.format(outdir, self.row['volume'], 'rāindex.csv'), 'a') as output:
                writer = csv.DictWriter(output, dayindex_fieldnames)
                writer.writerow(self.day)

    def __process_paragraphs(self, text):
        utterance = []
        while True:
            p_break = paragraph_pattern.search(text)
            if p_break:
                utterance = self.__process_paragraph(
                    text[:p_break.start()], utterance)

                text = text[p_break.end():]
            else:
                utterance = self.__process_paragraph(text, utterance)
                if utterance:
                    self.__write_row(utterance)
                break

    def __process_paragraph(self, text, utterance):
        kaikōrero = newspeaker_pattern[self.flag410].match(text)
        if kaikōrero:
            name = kaikōrero.group(1)
            if name:
                if utterance:
                    self.__write_row(utterance)
                    utterance = []
                self.row['speaker'] = clean_whitespace(name)
                text = text[kaikōrero.end():]

        return self.__process_sentences(text, utterance)

    def __process_sentences(self, text, utterance):
        consecutive = {'reo': True} if utterance else {'reo': False}
        consecutive['other'] = False
        loopflag, nums = True, {}

        while loopflag:
            nextsentence = new_sentence.search(text)
            if nextsentence:
                sentence = text[:nextsentence.start() + 1]
                text = text[nextsentence.end():]
            else:
                sentence = text
                loopflag = False

            c, nums = kupu_ratios(sentence, tohutō=False)
            if c:
                sentence = clean_whitespace(sentence)
                if consecutive['reo']:
                    utterance.append(sentence)
                else:
                    consecutive['reo'] = True
                    consecutive['other'] = False
                    self.row['utterance'] += 1
                    utterance = [sentence]

            else:
                if not consecutive['other']:
                    if utterance:
                        self.__write_row(utterance)
                    utterance = []
                    consecutive['other'] = True
                    consecutive['reo'] = False
                    self.row['utterance'] += 1

                if len(sentence) > 5:
                    for k, v in nums.items():
                        if k != 'percent':
                            self.totals[k] += v

            if not loopflag:
                return utterance

    def __write_row(self, text):
        text = ' '.join(text)
        first_letter = re.search('[a-zA-Z£]', text)
        l = len(text)
        if first_letter and l > 3:
            text = text[first_letter.start():]
            bad_egg = re.match(
                '([^ A-Z]+ )?[A-Z][^ ]*(([^a-zA-Z]+[^ A-Z]*){1,2}[A-Z][^ ]*)*(([^a-zA-Z]+[^ A-Z]*){2})?', text)
            if not bad_egg:
                bad_egg = re.match(
                    '([^ ]{1,3} )+[^ ]{1,3}', text)

            if not (bad_egg and bad_egg.group() == text):
                c, nums = kupu_ratios(text, tohutō=False)
                for k, v in nums.items():
                    if k != 'percent':
                        self.totals[k] += v

                # and not (nums['reo'] < 5 and nums['other'] + nums['ambiguous'] < 10):
                if c and nums['reo'] > 2 and nums['other'] < 20:
                    self.row['text'] = text
                    self.row.update(nums)
                    print(self.row['text'])
                    with open('{}/{}{}'.format(outdir, self.row['volume'], 'reomāori.csv'), 'a') as output:
                        writer = csv.DictWriter(output, reo_fieldnames)
                        writer.writerow(self.row)


# New header pattern from volume 359 onwards (5 Dec 1968), 440 onwards - first 3 lines, 466 onward - 1 line
header_pattern = re.compile(
    '[^\n]*\n((([^\n\]]*\n){0,5}[^\n]*\][^\n]*)\n)?((([^ \n]+( [^ \n,—]+){0,3}))\n)*(([^a-z]([^\n:—](?!([^a-zA-Z]+[a-z]+){3}))*( (?!O )[^a-z\n][^ —:\n]*){2}[^\-\n:]\n)+)*')
# best catch-all header pattern so far:
# ',"[^\n]*\n((([^\n\]]*\n){0,5}[^\n]*\][^\n]*)\n)?((([^ \n]+( [^ \n,—]+){0,3}))\n)*(([^a-z]([^\n:—](?!([^a-zA-Z]+[a-z]+){3}))*( (?!O )[^a-z\n][^ —:\n]*){2}[^-\n:]\n)+)*'


# Regex to look for meeting date. Date pattern changes from vol 294 onwards
date_pattern = [re.compile(
    r'\n[A-Z][a-z]{5,8}, [\dinISl&^]{1,2}[a-zA-Z]{2} [A-Z][!1Ia-z]{2,8}, [\d(A-Z]{4,5}'),
    re.compile(r'[A-Z][A-Za-z]{5,8}, \d{1,2} [A-Za-z]{3,9},? \d{4}[^\n–:!?]{0,4}\n')]

# Speaker pattern changes at volume 410 (19 May 1977). Pre-410 many passages are written
# as a narrative, so will process it as whole paragraphs.
newspeaker_pattern = [re.compile(
    '[^a-zA-Z\n]*([A-Z][^—:\n]*( ?[A-Z]){3,}(\s*\([a-zA-Z\s]*\))?)(((\.? ?—\-?)\s*(?=[A-Z£]))|[^a-zA-Z]+(?=said|asked|wished|did|in|replied|hoped|was|thought|supported|desired|obtained|moved|having|by|brought|seconded|announ(c|e)ed))'),
    re.compile(
    '([A-Z][^\n]*[)A-Z])(\s+replied)?[:;]')]
# Previous versions:
# NEW vs
# '(([-~‘’\'() a-zA-Z]*\n)*)([^:\n]*:|([^,\n]*\n)[^:\n]*:)'
# '((\d{d}\.|The) )?(((Rt\.?|Right) )?(Hon\. )?(Mr\. )?([A-Z]([a-z{a}]+|[A-Z{a}]+|\.?))([ -{a}][tA-Z]([öa-z{a}]+|[ÖA-Z{a}]+|\.?))+)([-—]+| \(|:)'.format(a=apostrophes, d='{1,2}')
# name_behaviour = '((\d{1,2}\.|The) )?(((Rt\.?|Right) )?(Hon\. )?(Mr\. )?([A-Z]([a-z‘’\']+|[A-Z‘’\']+|\.?))([ -‘’\'][tA-Z]([öa-z‘’\']+|[ÖA-Z‘’\']+|\.?))+)([-—]+| \(|:)'
# old vs
# '([A-Z .:—-]*\n)*[A-Z]([^(\n]+\([^-—\n]+[-—]*\n)?[a-zA-Z". ()]+\. ?[-—]+(?!\n)'


def main():
    try:
        process_csv_files()
        print('Corpus aggregation successful\n')
    except Exception as e:
        raise e
    finally:
        print("\n--- Job took {} ---".format(get_rate()))


start_time = time.time()


def get_rate():
    m, s = divmod(time.time() - start_time, 60)
    s = int(s)
    h, m = divmod(m, 60)
    if m:
        m = int(m)
        if h:
            return '{} hours {} minutes {} seconds'.format(int(h), m, s)
        else:
            return '{} minutes {} seconds'.format(m, s)
    return '{} seconds'.format(s)


if __name__ == '__main__':
    main()