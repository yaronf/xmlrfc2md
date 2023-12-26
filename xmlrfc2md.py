import xml.etree.ElementTree as ElementTree
import argparse
import logging
from typing import Any

import yaml  # pyyaml package
import sys
import textwrap

wrapper = textwrap.TextWrapper(width=120, replace_whitespace=False, break_on_hyphens=False)

internal_refs = []

messages: dict[Any, int] = {}


def throttle(msg_type, msg: str) -> None:
    global messages
    if msg_type not in messages:
        messages[msg_type] = 0
    if messages[msg_type] == 0:
        logging.warning(msg)
    messages[msg_type] += 1


def collapse_spaces(t: str, span=False):
    lines = t.splitlines()
    out = []
    for ln in lines:
        lst = ln.lstrip()
        if lst != ln:
            lst = " " + lst
        out.append(lst)
    if not span:
        return "\n".join(out)
    else:
        return " ".join(out)


def concat_with_space(s, t: str) -> str:
    if s == "" or t == "":
        return s + t
    if (s.endswith("(") or s.endswith("[") or s.endswith(".") or s.endswith("\"") or
            t.startswith(" ") or t.startswith("\n")):
        return s + t
    else:
        return s + " " + t


def extract_text(root: ElementTree):
    output = ""
    for para in root.findall("t"):
        output += para.text + "\n"
    return output


def section_title(elem: ElementTree, level: int):
    anchor_name = elem.get("anchor")
    anchor = ""
    if anchor_name is not None:
        internal_refs.append(anchor_name)
        anchor = "{#" + elem.get("anchor") + "}"
    name = elem.find("name")
    if name is None:
        logging.error("section with no name")
        return ""
    return "\n" + "#" * level + " " + name.text.strip() + " " + anchor + "\n"


def extract_xref(elem: ElementTree):
    target = elem.get("target")
    section = elem.get("section")
    section_format = elem.get("sectionFormat")
    fmt = elem.get("format")

    if target is None:
        logging.error("missing target in xref")
        return "badxref"
    if section is None:
        if fmt == "counter":
            return "{{<" + target + "}}"
        else:
            return "{{" + target + "}}"
    match section_format:
        case "of":
            return "Section " + section + " of {{" + target + "}}"
        case "comma":
            return "{{" + target + "}}, Section " + section
        case "parens":
            return "{{" + target + "}} (" + section + ")"
        case "bare":
            return section
        case _:
            logging.error("unsupported xref section format: " + section_format)
            return "badxref"


class Lists:
    NoType = 0
    Unordered = 1
    Ordered = 2
    Definition = 3


def extract_sourcecode(e: ElementTree) -> str:
    lang = e.get("type")
    if lang is None:
        return "\n~~~\n" + e.text + "\n~~~"
    else:
        throttle("warn-lang", "language tag for source code may be incorrect")
        return "\n~~~ " + lang + "\n" + e.text + "\n~~~"


def extract_figure(e: ElementTree) -> str:
    anchor = e.get("anchor")
    if anchor is None:
        logging.error("missing anchor for figure")
        return ""
    artset = e.find("./artset")
    if artset is not None:
        logging.warning(f"artset found for figure {anchor},"
                        f" Kramdown does not support raw SVG yet, extracting ASCII art")
        content = e.find("./artset/artwork[@type='ascii-art']")
        if content is None:
            logging.error(f"no ASCII art for {anchor}")
            return ""
    else:
        content = e.find("./artwork")
        if content is None:
            content = e.find("./sourcecode")
        if content is None:
            logging.warning(f"figure {anchor} has no content?")
            return ""
    name_el = e.find("./name")
    if name_el is not None:
        name = name_el.text
        return extract_sourcecode(content) + "\n{: #" + anchor + " title=\"" + name + "\"}\n"
    else:
        return extract_sourcecode(content)


def extract_table(root: ElementTree) -> str:
    output = ""
    thead = root.find("./thead")
    output += "\n"
    if thead is not None:
        tr = thead.find("./tr")
        if tr is None:
            logging.error("no tr in table head")
            return ""
        ths = tr.findall("./th")
        for th in ths:
            output += "|" + extract_sections(th, 0, 0, span=True)
        output += "\n"
        for th in ths:
            output += "|"
            align = th.get("align")
            if align is None:
                dash = "-"
            elif align == "left":
                dash = ":-"
            elif align == "center":
                dash = ":-:"
            else:
                dash = "-:"
            output += dash + " "
        output += "\n"
    tbody = root.find("./tbody")
    if tbody is None:
        logging.error("no body for table")
        return ""
    trs = tbody.findall("./tr")
    if len(trs) == 0:
        logging.error("no rows in table body")
        return ""
    for tr in trs:
        tds = tr.findall("./td")
        for td in tds:
            output += "|" + extract_sections(td, 0, 0, span=True)
        output += "\n"
    output += "\n"
    return output


def extract_sections(root: ElementTree, section_level: int, list_level: int, list_type=Lists.NoType, span=False) -> str:
    """Extract text from a sequence of <t> elements, possibly nested
"""
    output = ""
    if root.text is not None:
        output += collapse_spaces(root.text, span)
    for elem in root:
        match elem.tag:
            case "t":
                anchor = elem.get("anchor")
                if anchor is not None and not anchor.startswith("section-"):
                    output += "{: #" + anchor + "}\n"
                output += extract_sections(elem, section_level, list_level)
                output += "\n"
            case "blockquote":
                output += "> " + extract_sections(elem, section_level, list_level)
                output += "\n"
            case "li":
                output += extract_list(elem, section_level, list_level + 1, list_type)
                output += "\n"
            case "section":
                if elem.get("anchor") != "authors-addresses":
                    # Hack: kdrfc only adds this section if the title is missing
                    output += section_title(elem, section_level + 1)
                    output += extract_sections(elem, section_level + 1, 0)
                    output += "\n"
            case "ul":
                output += extract_sections(elem, section_level, list_level, Lists.Unordered)
            case "ol":
                output += extract_sections(elem, section_level, list_level, Lists.Ordered)
            case "dl":
                output += extract_sections(elem, section_level, list_level, Lists.Definition)
            case "dt":
                output += "\n" + extract_sections(elem, section_level, list_level, Lists.Definition)
            case "dd":
                output += ": " + extract_sections(elem, section_level, list_level).lstrip()
            case "xref":
                output = concat_with_space(output, extract_xref(elem))
            case "displayreference":
                pass
            case "bcp14":
                output = concat_with_space(output, elem.text)
            case "tt":
                output = concat_with_space(output, "`" + elem.text + "`")
            case "sup":
                output += "<sup>" + elem.text + "</sup>"
            case "contact":
                output += " " + elem.get("fullname")
            case "name" | "references" | "author":
                pass  # section name is processed by section_title(), references processed in extract_preamble(),
                # authors defined twice (?)
            case "sourcecode" | "artwork":
                output += extract_sourcecode(elem)
            case "figure":
                output += extract_figure(elem)
            case "table":
                output += extract_table(elem)
            case _:
                logging.error("skipping unknown element: %s", elem.tag)
        if elem.tail is not None:
            output += collapse_spaces(elem.tail, span)
    return output


def extract_list(root: ElementTree, section_level: int, list_level: int, list_type: int) -> str:
    if list_type == Lists.NoType:
        pre = ""
    elif list_type == Lists.Unordered:
        pre = "* "
    else:
        pre = "1. "
    output = ""
    ts = root.find("t")
    if ts is None or len(ts) == 0:
        output += pre + extract_sections(root, section_level, list_level).lstrip()
    else:
        output = ""
        is_first = True
        for elem in root:
            if elem.tag == "t":
                if is_first:
                    output += pre + extract_sections(elem, section_level, list_level).lstrip()
                    is_first = False
                else:
                    output += "    " * list_level + extract_sections(elem, section_level, list_level)
            else:
                output += extract_sections(elem, section_level, list_level)
            output += "\n"
    return output


def conditional_add(m: dict, key: str, value) -> None:
    if value is not None:
        m[key] = value


def extract_preamble(rfc: ElementTree) -> str:
    output = ""
    front = rfc.find("front")
    if front == "":
        sys.exit("No front block found")

    preamble = {}
    title_el = front.find("title")
    title = title_el.text
    conditional_add(preamble, "title", title)
    abbrev = title_el.get("abbrev")
    conditional_add(preamble, "abbrev", abbrev)
    docname = rfc.get("docName")
    conditional_add(preamble, "docname", docname)
    category = rfc.get("category")
    conditional_add(preamble, "category", category)
    ipr = rfc.get("ipr")
    conditional_add(preamble, "ipr", ipr)
    area = front.find("area").text
    conditional_add(preamble, "area", area)
    workgroup_el = front.find("workgroup")
    if workgroup_el is not None:
        conditional_add(preamble, "workgroup", workgroup_el.text)

    keywords = [el.text for el in front.findall("keyword")]
    preamble["keyword"] = keywords

    preamble["stand_alone"] = "yes"  # Magic required for some references to work

    # noinspection PyDictCreation
    pi = {}

    # The following directives are set by default, and may need to be configurable
    pi["rfcstyle"] = "yes"
    pi["strict"] = "yes"
    pi["comments"] = "yes"
    pi["inline"] = "yes"
    pi["text-list-symbols"] = "-o*+"
    pi["docmapping"] = "yes"

    tocinclude = rfc.get("tocInclude")
    if tocinclude == "true":
        pi["toc"] = "yes"
    tocdepth = rfc.get("tocDepth")
    if tocdepth is not None:
        pi["tocindent"] = "yes"  # No direct conversion
    sortrefs = rfc.get("sortRefs")
    if sortrefs == "true":
        pi["sortrefs"] = "yes"
    symrefs = rfc.get("symRefs")
    if symrefs == "true":
        pi["symrefs"] = "yes"

    preamble["pi"] = pi

    authors = convert_authors(front)
    preamble["author"] = authors

    normative = convert_references(rfc, "normative")
    informative = convert_references(rfc, "informative")

    # https://stackoverflow.com/questions/30134110/how-can-i-output-blank-value-in-python-yaml-file
    yaml.SafeDumper.add_representer(
        type(None),
        lambda dumper, value: dumper.represent_scalar(u'tag:yaml.org,2002:null', '')
    )

    output += yaml.safe_dump(preamble, default_flow_style=False)
    output += "\n\n"
    if normative is not None:
        output += yaml.safe_dump({"normative": normative}, default_flow_style=False)
    if informative is not None:
        output += yaml.safe_dump({"informative": informative}, default_flow_style=False)

    return output


def convert_authors(front: ElementTree) -> list[dict]:
    authors = []
    for a in front.findall("author"):
        author = {}
        initials = a.get("initials")
        surname = a.get("surname")
        if initials is not None and surname is not None:
            ins = initials + " " + surname
            author["ins"] = ins
        name = a.get("fullname")
        if name is not None:
            author["name"] = name
        org_el = a.find("organization")
        if org_el is not None:
            org = org_el.text
            if org:
                author["organization"] = org
        uri_el = a.find("uri")
        if uri_el is not None:
            uri = uri_el.text
            author["uri"] = uri
        email_el = a.find("address/email")
        if email_el is not None:
            email = email_el.text
            author["email"] = email

        authors.append(author)
    return authors


def find_references(rfc: ElementTree, ref_type: str) -> ElementTree:
    for block in rfc.findall("./back/references/references"):
        name_el = block.find("./name")
        if name_el is None:
            logging.error("no name for reference block")
            continue
        name = name_el.get("slugifiedName")
        if name == "name-" + ref_type + "-references":
            return block
    return None


def full_ref(ref: ElementTree) -> dict | None:
    out = {}
    target = ref.get("target")
    if target is not None:
        out["target"] = target
    front = ref.find("front")
    if front is None:
        logging.error("reference with no front")
        return None
    title_el = front.find("title")
    if title_el is None:
        logging.error("reference with no title")
        return None
    out["title"] = title_el.text
    date_el = front.find("date")
    if date_el is not None:
        month = date_el.get("month")
        year = date_el.get("year")
        if month:
            date = month + " " + year
        else:
            date = year
        out["date"] = date
    authors = convert_authors(front)
    out["author"] = authors
    return out


def convert_references(rfc: ElementTree, ref_type: str) -> dict | None:
    ref_block = find_references(rfc, ref_type)
    if ref_block is None:
        logging.warning(f"no {ref_type} references?")
        return None
    ref_list = ref_block.findall("./reference")
    if len(ref_list) == 0:
        logging.warning(f"no {ref_type} references?")
        return None
    refs = {}
    for ref in ref_list:
        anchor = ref.get("anchor")
        if anchor is None:
            logging.warning("reference missing an anchor")
            continue
        if (anchor.startswith("RFC") or anchor.startswith("I-D.") or anchor.startswith("BCP") or
                anchor.startswith("STD")):
            refs[anchor] = None
            continue
        target = ref.get("target")
        if target is not None and target.startswith("https://doi.org/"):
            doi = target.removeprefix("https://doi.org/")
            refs[anchor] = "DOI." + doi
            continue
        converted = full_ref(ref)
        if converted is not None:
            refs[anchor] = converted

    ref_groups = ref_block.findall("./referencegroup")
    for group in ref_groups:
        anchor = group.get("anchor")
        if anchor is None:
            logging.warning("reference missing an anchor")
            continue
        if anchor.startswith("BCP") or anchor.startswith("STD"):
            refs[anchor] = None
            continue
        else:
            logging.warning("unexpected reference group")
            continue

    return refs


def fill_text(text: str) -> str:
    """https://stackoverflow.com/questions/57081970/python-textwrap-with-n-is-placing-newline-mid-paragraph"""
    paragraphs = text.splitlines()
    text_out = "\n".join([
        wrapper.fill(p) for p in paragraphs
    ])
    return text_out


def parse_rfc(infile: str, fill: bool):
    output = ""
    tree = ElementTree.parse(infile)
    root = tree.getroot()
    if root.tag != "rfc":
        sys.exit("Tag not found:\"rfc\"")

    t = extract_preamble(root)
    output += "---\n"
    output += t
    output += "\n"

    abstract = root.find("front/abstract")
    if abstract == "":
        sys.exit("No abstract found")
    t = extract_text(abstract)
    output += "--- abstract\n\n"
    output += t
    output += "\n\n"

    middle = root.find("middle")
    if middle == "":
        sys.exit("Cannot find middle part of document")
    extracted = extract_sections(middle, 0, False)
    if not fill:
        t = extracted
    else:
        t = fill_text(extracted)
    output += "--- middle\n\n"
    output += t

    back = root.find("back")
    if back != "":
        extracted = extract_sections(back, 0, False)
        if not fill:
            t = extracted
        else:
            t = fill_text(extracted)
        output += "--- back\n\n"
        output += t

    return output


def main():
    parser = argparse.ArgumentParser(description='Convert a published RFC from XML to Markdown')
    parser.add_argument('infile', help='input XML file')
    parser.add_argument('outfile', help='output Markdown file')
    parser.add_argument('--fill', '-f', action=argparse.BooleanOptionalAction,
                        help='fill paragraphs (might break some markdown)')
    args = parser.parse_args()

    logging.basicConfig(format='%(levelname)s: %(message)s', level=logging.DEBUG)

    markdown = parse_rfc(args.infile, args.fill)
    out = open(args.outfile, "w")
    out.write(markdown)


if __name__ == "__main__":
    main()
