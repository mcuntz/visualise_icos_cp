#!/usr/bin/env python
'''
Visualise ICOS ecosystem data from the ICOS Carbon Portal (ICOS-CP)

usage: make_html.py [-h] [-d number_days] [-p product] [args]

Make visualisation for FR-Hes.

positional arguments:
  args                  ICOS Ecosystem station name

options:
  -h, --help            show this help message and exit
  -d number_days, --days number_days
                        Number of days to visualise. 0 means all available days
                        (default: 0).
  -p product, --product product
                        ICOS CP data product: "NRT" or "FLUXNET"
                        (default: NRT).

Examples
--------
# Visualise the last 30 days
  python make_html.py FR-Hes -d 30

History
-------
Written, May 2023, Matthias Cuntz

'''
import argparse
import calendar as cal
import datetime as dt
import glob
import re
import os
import numpy as np
import hvplot.pandas  # needed to extend pandas with hvplot
import pandas as pd
import hvplot.xarray  # needed to extend xarray with hvplot
import xarray as xr
import hvplot
import holoviews
from bokeh.resources import INLINE

import warnings
warnings.simplefilter("ignore", FutureWarning)
from icoscp.cpauth.authentication import Authentication
from icoscp.station import station
from icoscp.cpb.dobj import Dobj

# For testing offline
geticos = True     # True/False: get from ICOS-CP/Read from local (numpy) files
writeicos = False  # True: Write numpy files of ICOS data if geticos==True


#
# Functions
#

def read_icos(istation, product='NRT', level=None):
    '''
    List of pandas DataFrame of ICOS-CP all levels for `product`

    Parameters
    ----------
    istation : str
        ICOS ecosystem station code
    product : str, optional
        ICOS-CP data product (deault: 'NRT')

           NRT = near-real-time data
           FLUXNET = products from europe-fluxdata.eu

    level : int, optional
        filter to dataobjects (default: None)

            1 = raw data
            2 = QAQC data
            3 = elaborated products

    Returns
    -------
    List of pandas DataFrame with ICOS-CP data products

    '''
    # all data products
    if product.lower() == 'nrt':
        speclabel = ['ETC NRT Fluxes',
                     'ETC NRT Meteosens']
    elif product.lower() == 'fluxnet':
        speclabel = ['Fluxnet Archive Product',
                     'Fluxnet Product']
    else:
        raise ValueError(f'Product not known: {product}.'
                         f' Known products: ["NRT", "FLUXNET"].')

    # Authenticate at ICOS Carbon Portal
    Authentication()

    # thestation data object for the required station
    thestation = station.get(istation)

    # dataobjects contains all dataobjects for datalevel 1 of the station
    dataobjects = thestation.data(level=level)

    df = []
    for ss in speclabel:
        # select the dataobjects of the required data specification
        obj = dataobjects[dataobjects['specLabel'] == ss].dobj
        # we take the first dataobject from the list
        # (and assume that there is only one, as it should)
        try:
            thedobj = Dobj(obj.iloc[0])
            # load the dataframe with the data into idf
            # one might be asked for its ICOS-CP login and password
            idf = thedobj.data
            df.append(idf)
        except:
            pass

    return df


def check_variable(ss, cc, df, df_page, idf):
    '''
    Check if string `ss` matches variable `cc`

    Parameters
    ----------
    ss : str
        Code of variable in Variable column of plot_guide
    cc : str
        Column name in DataFrame
    df : pandas.DataFrame
        `df[['TIMESTAMP', cc]]`
    df_page : pandas.DataFrame
        Current line of df_plot_guide
    idf : pandas.DataFrame
        DataFrame for `ss`

    Returns
    -------
    title, depths, DataFrame
        Valued if `ss` matches `cc`, or None

    '''
    otitle = None
    odepths = None
    odf = None

    # Allow TA_1_ for TA_1_.*
    if ss.endswith('_'):
        ss = ss + '.*'

    m = re.fullmatch(ss, cc)
    if m is not None:
        otitle = df_page['Title']

        if isinstance(df_page['Depths'], str):
            odepths = [ float(d)
                        for d in df_page['Depths'].split() ]
        else:
            odepths = []

        odf = df.copy()
        odf.set_index('TIMESTAMP', inplace=True)

    return otitle, odepths, odf


def get_variables_page(df, df_plot_guide, page, days=0):
    '''
    Get all variables for panels on page

    Parameters
    ----------
    df : list
        List of pandas.DataFrame
    df_plot_guide : pandas.DataFrame
        plot_guide.csv read into DataFrame
    page : str
        Page to process
    days : int
        Days to include in plot (default: 0). Take all available days
        if `days == 0`.

    Returns
    -------
    titles, variables, depths
        Lists for panels of current `page`

    '''
    if days > 0:
        # time span: [first_date, today]
        today = dt.datetime.today()
        first_date = today - dt.timedelta(days=days)

    # select page from plot_guide
    df_page = df_plot_guide[df_plot_guide['Page'] == page]
    npanel = df_page.shape[0]
    titles = []
    variables = []
    depths = []
    for ii in range(npanel):
        ivars = df_page['Variable'].iloc[ii]
        svars = ivars.split('+')
        svars = [ ss.strip() for ss in svars ]
        for dd in df:  # data streams on carbon portal
            idf = None
            for ss in svars:  # variables in plot_guide
                for cc in dd.columns:  # columns in current stream
                    otitle, odepths, odf = check_variable(
                        ss, cc, dd[['TIMESTAMP', cc]], df_page.iloc[ii], idf)
                    if (otitle is not None) and (idf is None):
                        titles.append(otitle)
                    if (odepths is not None) and (idf is None):
                        depths.append(odepths)
                    if (odf is not None) and (idf is None):
                        idf = odf.copy()
                    elif (odf is not None) and (idf is not None):
                        idf = pd.concat([idf, odf], axis=1)
            if idf is not None:
                if days > 0:
                    idf = idf[(idf.index >= first_date) &
                              (idf.index <= today)]
                variables.append(idf)

    return titles, variables, depths


def layout_page(df, page, plot_guide='plot_guide.csv', days=0):
    '''
    Make all panels for `page`

    Parameters
    ----------
    df : list
        List of pandas.DataFrame
    page : str
        Name of page in plot_guide.csv
    plot_guide : str or pandas.DataFrame
        CSV file or pandas.DataFrame with variables in panels and pages
    days : int
        Days to include in plot (default: 0). Take all available days
        if `days == 0`.

    Returns
    -------
    holoviews.Layout

    '''
    # get plot_guide
    if isinstance(plot_guide, pd.core.frame.DataFrame):
        df_plot_guide = plot_guide
    elif isinstance(plot_guide, str):
        df_plot_guide = pd.read_csv(plot_guide, sep=',', header=0)
    else:
        raise ValueError('plot_guide must be str or Pandas DataFrame: '
                         + str(type(plot_guide)))

    # time span: [first_date, today]
    today = dt.datetime.today()
    first_date = today - dt.timedelta(days=days)
    first_year = first_date.year

    # get variables for panels on page
    titles, variables, depths = get_variables_page(df, df_plot_guide, page,
                                                   days=days)

    # setup plot
    pstyle = {'xaxis': 'bottom',
              'yaxis': 'left',
              'grid': False,
              'legend': 'right',
              'padding': 1}
    lstyle = pstyle.copy()
    lstyle.update({'line_width': 1})
    mstyle = pstyle.copy()
    mstyle.update({'marker': 'o',
                   'size': 3})

    panels = []
    for iv in range(len(titles)):
        tit = titles[iv]
        ytit = tit.replace(' profile', '')
        idf = variables[iv]
        depth = depths[iv]
        if page.endswith('2D'):
            if 'temperature' in tit:
                cmap = 'RdBu_r'
            else:
                cmap = 'RdBu'
            first_days = 366 if cal.isleap(first_year) else 365
            add_days = [ first_days * (dd.year - first_year)
                         for dd in idf.index ]
            x = [ dd.day_of_year + add_days[ii]
                  for ii, dd in enumerate(idf.index) ]
            y = np.array(depth)
            z = idf.to_numpy().astype(float).T
            if not np.all(np.isnan(z)):
                ds = xr.DataArray(z, coords=[y, x],
                                  dims=["depths", "day-of-year"])
                shades = ds.hvplot.contourf(levels=9, title=titles[iv],
                                            cmap=cmap)
                panels.append(shades)
        else:
            lines = idf.hvplot.line(title=tit, ylabel=ytit,
                                    **lstyle)
            markers = idf.hvplot.scatter(**mstyle)
            pp = lines * markers
            pp = pp.opts(shared_axes=False)
            panels.append(pp)
    layout = panels[0]
    for pp in panels[1:]:
        layout = layout + pp
    if isinstance(layout, holoviews.core.layout.Layout):
        layout = layout.cols(2)

    return layout


if __name__ == '__main__':

    #
    # Command line
    #

    days = 0
    product = 'NRT'
    istation = ''
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=('''Make visualisation for FR-Hes.'''))
    parser.add_argument('-d', '--days', action='store', type=int,
                        default=days, dest='days', metavar='number_days',
                        help=('Number of days to visualise. 0 means all'
                              ' available days (default: ' + str(days) + ').'))
    parser.add_argument('-p', '--product', action='store', type=str,
                        default=product, dest='product', metavar='product',
                        help=(f'ICOS CP data product: "NRT" or "FLUXNET"'
                              f' (default: {product}).'))
    parser.add_argument('cargs', nargs='?', default=istation,
                        metavar='args', help='ICOS Ecosystem station name')
    args = parser.parse_args()
    days = args.days
    product = args.product
    istation = args.cargs

    del parser, args

    if istation == '':
        raise ValueError('Station name must be given.')

    #
    # Read data
    #

    if geticos:
        df = read_icos(istation, product=product, level=None)
        if writeicos:
            for ii, dd in enumerate(df):
                ofile = istation + '_' + str(ii) + '.npz'
                np.savez(ofile, index=dd.index, values=dd.values,
                         columns=list(dd.columns))
    else:
        df = []
        allnpz = glob.glob(istation + '_*.npz')
        allnpz.sort()
        for ff in allnpz:
            dat = np.load(ff, allow_pickle=True)
            df.append(pd.DataFrame(dat['values'], index=dat['index'],
                                   columns=dat['columns']))

    # Check available variables
    print('Variables available')
    for dd in df:
        print(list(dd.columns))

    # read plot guide
    df_plot_guide = pd.read_csv('plot_guide.csv', sep=',', header=0)

    #
    # Make html
    #

    if not os.path.exists('html'):
        os.mkdir('html')

    # index.html
    with open('index.html', 'w') as ff:
        print('<!DOCTYPE html public "-//W3C//DTD HTML'
              ' 4.01 Frameset//EN"\n'
              ' "http://www.w3.org/TR/html4/frameset.dtd">\n'
              '<html>\n'
              '    <head>\n'
              '        <title>ICOS-CP data</title>\n'
              '    </head>\n'
              '    <frameset cols="15%, 85%">\n'
              '        <frame name="fixed" src="html/menu.html">\n'
              '        <frame name="dynamic" src="html/empty.html">\n'
              '    </frameset>\n'
              '</html>', file=ff)

    # empty.html
    with open('html/empty.html', 'w') as ff:
        print('<!DOCTYPE html public "-//W3C//DTD HTML 4.01'
              ' Frameset//EN"\n'
              ' "http://www.w3.org/TR/html4/frameset.dtd">\n'
              '<html>\n'
              '    <body>\n'
              '    </body>\n'
              '</html>', file=ff)

    # beginning of menu.html
    fhtml = open('html/menu.html', 'w')
    print('<!DOCTYPE html public "-//W3C//DTD HTML'
          ' 4.01 Transitional//EN"\n'
          ' "http://www.w3.org/TR/html4/loose.dtd">\n'
          '<html>\n'
          '    <head>\n'
          '        <title>ICOS-CP data frame</title>\n'
          '        <base href="html" target="dynamic">\n'
          '    </head>\n'
          '    <body>\n',
          file=fhtml)

    # individual pages.html
    print('\nWrite pages')
    # for pp in ['soil2D']:
    for pp in ['air', 'radiation', 'soil', 'soil2D', 'flux']:
        print(f'  {pp}')
        ihtml = layout_page(df, pp, plot_guide=df_plot_guide, days=days)
        hvplot.save(ihtml, 'html/' + pp + '.html', resources=INLINE)
        print('        <p><a href="' + pp + '.html" target="dynamic">' +
              pp + '</a>', file=fhtml)

    # end of menu.html
    print('    </body>', file=fhtml)
    print('</html>', file=fhtml)
    fhtml.close()
